"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ButtonLink, Card, Dialog, SafetyText } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import type { ChatMessageItem, ChatTurnResponse, TriageResultItem } from "@/types/api";
import { UK_TIME_ZONE } from "@/lib/format";

const time = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
});

const BANDS: Record<string, { labelKey: MessageKey; border: string; dot: string }> = {
  URGENT: {
    labelKey: "symptomCheck.band.URGENT",
    border: "border-nhs-orange",
    dot: "bg-nhs-orange",
  },
  SOON: { labelKey: "symptomCheck.band.SOON", border: "border-nhs-blue", dot: "bg-nhs-blue" },
  ROUTINE: {
    labelKey: "symptomCheck.band.ROUTINE",
    border: "border-nhs-mid-grey",
    dot: "bg-nhs-mid-grey",
  },
  SELF_CARE: {
    labelKey: "symptomCheck.band.SELF_CARE",
    border: "border-nhs-mid-grey",
    dot: "bg-nhs-mid-grey",
  },
};

/**
 * The emergency call to action.
 *
 * Rendered above the conversation rather than after it. Previously the 999 instruction sat
 * below the transcript and below the fold - the one message that must be seen instantly
 * was the one that needed scrolling to reach.
 *
 * It also appears exactly once. The same instruction was previously repeated in the chat
 * bubble, an escalation banner and twice more in the outcome panel; four identical
 * warnings read as noise and blunt the one that matters.
 */
function EmergencyNotice() {
  const t = useT();

  return (
    <section
      aria-labelledby="emergency-heading"
      className="mb-6 border-4 border-nhs-red bg-white"
    >
      <div className="bg-nhs-red px-5 py-3">
        <h2 id="emergency-heading" className="flex items-center gap-3 text-2xl font-bold text-white">
          <span
            aria-hidden="true"
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-white text-lg font-bold text-nhs-red"
          >
            !
          </span>
          <SafetyText id="symptomCheck.emergency.title" />
        </h2>
      </div>

      <div className="p-5">
        <p className="mb-4 text-lg">
          <SafetyText id="symptomCheck.emergency.body" />
        </p>

        <div className="flex flex-wrap items-center gap-4">
          {/* tel: works on a phone, which is where a patient in this situation most likely
              is. On desktop it is still the clearest statement of the action. */}
          <a
            href="tel:999"
            className="inline-flex min-h-[52px] items-center rounded bg-nhs-red px-6 py-3 text-lg font-bold text-white no-underline shadow-[inset_0_-4px_0_0_#7c1509] hover:bg-[#b31c12] hover:text-white"
          >
            {t("symptomCheck.emergency.call")}
          </a>
          <p className="text-sm text-nhs-dark-grey">
            <SafetyText id="symptomCheck.emergency.orAande" />
          </p>
        </div>
      </div>
    </section>
  );
}

function Message({ message }: { message: ChatMessageItem }) {
  const t = useT();

  if (message.role === "SYSTEM") {
    return (
      <li className="mx-auto max-w-lg border border-nhs-mid-grey bg-nhs-pale-grey px-4 py-3 text-center text-sm">
        {message.content}
      </li>
    );
  }

  const fromPatient = message.role === "PATIENT";

  return (
    <li className={cn("flex flex-col gap-1", fromPatient ? "items-end" : "items-start")}>
      <span className="px-1 text-xs font-bold uppercase tracking-wide text-nhs-dark-grey">
        {/* Machine-generated content is always labelled. A patient must never be left to
            infer whether they are reading a person. */}
        {fromPatient ? t("symptomCheck.you") : t("symptomCheck.automatedCheck")}
        <span className="sr-only"> at {time.format(new Date(message.createdAt))}</span>
      </span>
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-line px-4 py-3 text-base leading-relaxed",
          fromPatient
            ? "rounded-l-lg rounded-tr-lg bg-nhs-blue text-white"
            : "rounded-r-lg rounded-tl-lg border border-nhs-mid-grey bg-white",
        )}
      >
        {message.content}
      </div>
    </li>
  );
}

function Outcome({ triage }: { triage: TriageResultItem }) {
  const t = useT();

  // The emergency case is handled by EmergencyNotice at the top of the page. Repeating the
  // instruction here is what made the screen read as four separate warnings.
  if (triage.severity === "EMERGENCY") return null;

  const band = BANDS[triage.severity] ?? BANDS.SOON;

  return (
    <Card
      title={t("symptomCheck.outcome.title")}
      className={cn("border-4", band.border)}
      headingLevel={2}
    >
      <div className="mb-3 flex items-center gap-3">
        <span aria-hidden="true" className={cn("size-4 shrink-0 rounded-full", band.dot)} />
        <strong className="text-xl">
          <SafetyText id={band.labelKey} />
        </strong>
      </div>

      <p className="mb-5">{triage.recommendedAction}</p>

      <ButtonLink href="/appointments/book" size="lg">
        {t("symptomCheck.outcome.seeAppointments")}
      </ButtonLink>

      <p className="mt-5 border-t border-nhs-pale-grey pt-4 text-sm text-nhs-dark-grey">
        <strong>
          <SafetyText id="symptomCheck.outcome.notADiagnosis" />
        </strong>{" "}
        <SafetyText
          id="symptomCheck.outcome.producedBy"
          values={{ engine: `${triage.engine} ${triage.engineVersion}` }}
        />{" "}
        <SafetyText id="symptomCheck.outcome.ifWorse" />
      </p>
    </Card>
  );
}

export default function SymptomCheckPage() {
  const queryClient = useQueryClient();
  const t = useT();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const conversation = useQuery({
    queryKey: ["chat", sessionId],
    queryFn: () => api.get<ChatTurnResponse>(`/chat/sessions/${sessionId}`),
    enabled: sessionId !== null,
  });

  const startSession = useMutation({
    mutationFn: () => api.post<ChatTurnResponse>("/chat/sessions"),
    onSuccess: (turn) => {
      setSessionId(turn.session.id);
      queryClient.setQueryData(["chat", turn.session.id], turn);
      setSendError(null);
      setConfirmRestart(false);
    },
  });

  const send = useMutation({
    mutationFn: (content: string) =>
      api.post<ChatTurnResponse>(`/chat/sessions/${sessionId}/messages`, { content }),
    onSuccess: (turn) => {
      queryClient.setQueryData(["chat", turn.session.id], turn);
      setDraft("");
      setSendError(null);
      inputRef.current?.focus();
    },
    onError: (error) =>
      setSendError(
        error instanceof ApiError ? error.message : "We could not send that. Please try again.",
      ),
  });

  const turn = conversation.data ?? startSession.data ?? null;
  const isEmergency = turn?.triage?.severity === "EMERGENCY";

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [turn?.messages.length]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.trim()) send.mutate(draft.trim());
  }

  function restart() {
    setSessionId(null);
    setDraft("");
    setSendError(null);
    // reset() before mutate(): a mutation keeps its previous data while the next one is in
    // flight, so without this the finished conversation flashes back on screen for a
    // moment before the new one arrives.
    startSession.reset();
    startSession.mutate();
  }

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mb-2 text-4xl font-bold">{t("symptomCheck.title")}</h1>
          <p className="max-w-2xl text-nhs-dark-grey">
            {t("symptomCheck.intro")}
          </p>
        </div>

        {/* Always available, including after the conversation ends. Without it, a mistyped
            or half-finished message left the patient at a dead end with no way back. */}
        {turn && (
          <Button
            variant="secondary"
            onClick={() => (turn.isClosed ? restart() : setConfirmRestart(true))}
          >
            {t("symptomCheck.startAgain")}
          </Button>
        )}
      </div>

      {isEmergency && <EmergencyNotice />}

      {!turn && (
        <Card title={t("symptomCheck.start.title")}>
          <p className="mb-2">{t("symptomCheck.start.body")}</p>
          <p className="mb-5 text-sm text-nhs-dark-grey">
            If this is an emergency, call <strong>999</strong> rather than using this check.
            For urgent advice call <strong>NHS 111</strong>.
          </p>
          <Button
            size="lg"
            loading={startSession.isPending}
            loadingText={t("common.loading")}
            onClick={() => startSession.mutate()}
          >
            {t("symptomCheck.start.action")}
          </Button>
          {startSession.error && (
            <Alert tone="error" title="Could not start" focusOnMount>
              {startSession.error.message}
            </Alert>
          )}
        </Card>
      )}

      {turn && (
        <>
          <section
            aria-label={t("symptomCheck.conversation")}
            className="mb-6 rounded border border-nhs-mid-grey bg-[#f7f9fa] p-5"
          >
            <ul
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              className="flex flex-col gap-5"
            >
              {turn.messages.map((message) => (
                <Message key={message.id} message={message} />
              ))}
            </ul>
            <div ref={endRef} />
          </section>

          {sendError && (
            <Alert tone="error" title="Could not send your message" focusOnMount>
              {sendError}
            </Alert>
          )}

          {!turn.isClosed && (
            <form onSubmit={handleSubmit} className="mb-6">
              <label htmlFor="reply" className="mb-1 block font-bold">
                {t("symptomCheck.reply.label")}
              </label>
              <p id="reply-hint" className="mb-2 text-sm text-nhs-dark-grey">
                {t("symptomCheck.reply.hint")}
              </p>
              <div className="flex flex-wrap gap-3">
                <input
                  ref={inputRef}
                  id="reply"
                  name="reply"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  aria-describedby="reply-hint"
                  maxLength={1000}
                  autoComplete="off"
                  disabled={send.isPending}
                  className="min-h-[44px] flex-1 rounded border-2 border-nhs-black px-3 py-2 text-base disabled:bg-nhs-pale-grey"
                />
                <Button
                  type="submit"
                  loading={send.isPending}
                  loadingText={t("symptomCheck.reply.sending")}
                  disabled={!draft.trim()}
                >
                  {t("symptomCheck.reply.send")}
                </Button>
              </div>
            </form>
          )}

          {turn.isClosed && !isEmergency && turn.session.status === "ESCALATED" && (
            <Alert tone="warning" title={t("symptomCheck.escalated.title")}>
              <SafetyText id="symptomCheck.escalated.body" />
            </Alert>
          )}

          {turn.triage && <Outcome triage={turn.triage} />}

          {turn.isClosed && (
            <p className="mt-6">
              <Button variant="secondary" onClick={restart} loading={startSession.isPending}>
                {t("symptomCheck.startNew")}
              </Button>
            </p>
          )}
        </>
      )}

      <p className="mt-8 text-sm text-nhs-dark-grey">
        <Link href="/dashboard">{t("common.back")}</Link>
      </p>

      <Dialog
        open={confirmRestart}
        onClose={() => setConfirmRestart(false)}
        title={t("symptomCheck.restart.title")}
        actions={
          <>
            <Button variant="secondary" onClick={() => setConfirmRestart(false)}>
              {t("symptomCheck.restart.keepGoing")}
            </Button>
            <Button variant="warning" onClick={restart} loading={startSession.isPending}>
              {t("symptomCheck.startAgain")}
            </Button>
          </>
        }
      >
        <p>
          {t("symptomCheck.restart.body")}
        </p>
      </Dialog>
    </>
  );
}
