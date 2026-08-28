"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ButtonLink, Card, Dialog } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import type { ChatMessageItem, ChatTurnResponse, TriageResultItem } from "@/types/api";

const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

const BANDS: Record<string, { label: string; border: string; dot: string }> = {
  URGENT: { label: "Be seen within 24 hours", border: "border-nhs-orange", dot: "bg-nhs-orange" },
  SOON: { label: "Be seen within a week", border: "border-nhs-blue", dot: "bg-nhs-blue" },
  ROUTINE: { label: "A routine appointment", border: "border-nhs-mid-grey", dot: "bg-nhs-mid-grey" },
  SELF_CARE: { label: "Self care", border: "border-nhs-mid-grey", dot: "bg-nhs-mid-grey" },
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
          Call 999 now
        </h2>
      </div>

      <div className="p-5">
        <p className="mb-4 text-lg">
          What you have described needs emergency help. Do not wait for an appointment, and
          do not drive yourself.
        </p>

        <div className="flex flex-wrap items-center gap-4">
          {/* tel: works on a phone, which is where a patient in this situation most likely
              is. On desktop it is still the clearest statement of the action. */}
          <a
            href="tel:999"
            className="inline-flex min-h-[52px] items-center rounded bg-nhs-red px-6 py-3 text-lg font-bold text-white no-underline shadow-[inset_0_-4px_0_0_#7c1509] hover:bg-[#b31c12] hover:text-white"
          >
            Call 999
          </a>
          <p className="text-sm text-nhs-dark-grey">
            Or go to your nearest A&amp;E.
          </p>
        </div>
      </div>
    </section>
  );
}

function Message({ message }: { message: ChatMessageItem }) {
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
        {fromPatient ? "You" : "Automated check"}
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
  // The emergency case is handled by EmergencyNotice at the top of the page. Repeating the
  // instruction here is what made the screen read as four separate warnings.
  if (triage.severity === "EMERGENCY") return null;

  const band = BANDS[triage.severity] ?? BANDS.SOON;

  return (
    <Card title="What we suggest" className={cn("border-4", band.border)} headingLevel={2}>
      <div className="mb-3 flex items-center gap-3">
        <span aria-hidden="true" className={cn("size-4 shrink-0 rounded-full", band.dot)} />
        <strong className="text-xl">{band.label}</strong>
      </div>

      <p className="mb-5">{triage.recommendedAction}</p>

      <ButtonLink href="/appointments/book" size="lg">
        See appointments
      </ButtonLink>

      <p className="mt-5 border-t border-nhs-pale-grey pt-4 text-sm text-nhs-dark-grey">
        <strong>This is not a diagnosis.</strong> It is an automated suggestion to help you
        choose an appointment, produced by{" "}
        <span className="font-mono">
          {triage.engine} {triage.engineVersion}
        </span>
        . A clinician has not yet reviewed it. If you feel worse, call NHS 111, or 999 in an
        emergency.
      </p>
    </Card>
  );
}

export default function SymptomCheckPage() {
  const queryClient = useQueryClient();
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
          <h1 className="mb-2 text-4xl font-bold">Symptom check</h1>
          <p className="max-w-2xl text-nhs-dark-grey">
            Describe how you are feeling and we will help you find the right appointment.
            This is an automated check, not a clinician, and it does not diagnose.
          </p>
        </div>

        {/* Always available, including after the conversation ends. Without it, a mistyped
            or half-finished message left the patient at a dead end with no way back. */}
        {turn && (
          <Button
            variant="secondary"
            onClick={() => (turn.isClosed ? restart() : setConfirmRestart(true))}
          >
            Start again
          </Button>
        )}
      </div>

      {isEmergency && <EmergencyNotice />}

      {!turn && (
        <Card title="Start a symptom check">
          <p className="mb-2">We will ask a few short questions. You can stop at any time.</p>
          <p className="mb-5 text-sm text-nhs-dark-grey">
            If this is an emergency, call <strong>999</strong> rather than using this check.
            For urgent advice call <strong>NHS 111</strong>.
          </p>
          <Button
            size="lg"
            loading={startSession.isPending}
            loadingText="Starting"
            onClick={() => startSession.mutate()}
          >
            Start
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
            aria-label="Conversation"
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
                Your reply
              </label>
              <p id="reply-hint" className="mb-2 text-sm text-nhs-dark-grey">
                Describe things in your own words. You can start again at any point.
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
                  loadingText="Sending"
                  disabled={!draft.trim()}
                >
                  Send
                </Button>
              </div>
            </form>
          )}

          {turn.isClosed && !isEmergency && turn.session.status === "ESCALATED" && (
            <Alert tone="warning" title="Passed to a member of staff">
              We have stopped asking questions. Someone will look at this.
            </Alert>
          )}

          {turn.triage && <Outcome triage={turn.triage} />}

          {turn.isClosed && (
            <p className="mt-6">
              <Button variant="secondary" onClick={restart} loading={startSession.isPending}>
                Start a new check
              </Button>
            </p>
          )}
        </>
      )}

      <p className="mt-8 text-sm text-nhs-dark-grey">
        <Link href="/dashboard">Back to your account</Link>
      </p>

      <Dialog
        open={confirmRestart}
        onClose={() => setConfirmRestart(false)}
        title="Start again?"
        actions={
          <>
            <Button variant="secondary" onClick={() => setConfirmRestart(false)}>
              Keep going
            </Button>
            <Button variant="warning" onClick={restart} loading={startSession.isPending}>
              Start again
            </Button>
          </>
        }
      >
        <p>
          This check will be discarded and a new one started. Nothing you have typed so far
          will be used to suggest an appointment.
        </p>
      </Dialog>
    </>
  );
}
