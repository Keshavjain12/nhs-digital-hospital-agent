"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ButtonLink, Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import type { ChatMessageItem, ChatTurnResponse, TriageResultItem } from "@/types/api";

const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** Colour, icon and words for each band. Never colour alone. */
const BANDS: Record<string, { label: string; border: string; badge: string; icon: string }> = {
  EMERGENCY: {
    label: "Emergency",
    border: "border-nhs-red",
    badge: "bg-nhs-red text-white",
    icon: "!",
  },
  URGENT: {
    label: "Within 24 hours",
    border: "border-nhs-orange",
    badge: "bg-nhs-orange text-nhs-black",
    icon: "!",
  },
  SOON: {
    label: "Within a week",
    border: "border-nhs-blue",
    badge: "bg-nhs-blue text-white",
    icon: "i",
  },
  ROUTINE: {
    label: "Routine",
    border: "border-nhs-mid-grey",
    badge: "bg-nhs-mid-grey text-white",
    icon: "i",
  },
  SELF_CARE: {
    label: "Self care",
    border: "border-nhs-mid-grey",
    badge: "bg-nhs-mid-grey text-white",
    icon: "i",
  },
};

function Message({ message }: { message: ChatMessageItem }) {
  if (message.role === "SYSTEM") {
    return (
      <li className="border-l-8 border-nhs-dark-grey bg-[#f7f9fa] p-4">
        <p className="mb-1 text-xs font-bold uppercase tracking-wide text-nhs-dark-grey">
          System
        </p>
        <p>{message.content}</p>
      </li>
    );
  }

  const fromPatient = message.role === "PATIENT";

  return (
    <li className={cn("flex flex-col", fromPatient && "items-end")}>
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-nhs-dark-grey">
        {/* Machine-generated content is always labelled as such. A patient must never be
            left to infer whether they are reading a person. */}
        {fromPatient ? "You" : "Automated check"}
        {!fromPatient && message.producedBy ? ` · ${message.producedBy}` : ""}
        <span className="sr-only"> at {time.format(new Date(message.createdAt))}</span>
      </p>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-line p-3",
          fromPatient
            ? "bg-nhs-blue text-white"
            : "border border-nhs-mid-grey bg-white text-nhs-black",
        )}
      >
        {message.content}
      </div>
    </li>
  );
}

function TriageOutcome({ triage }: { triage: TriageResultItem }) {
  const band = BANDS[triage.severity] ?? BANDS.SOON;
  const isEmergency = triage.severity === "EMERGENCY";

  return (
    <Card
      title="What we suggest"
      className={cn("border-4", band.border)}
      headingLevel={2}
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span
          className={cn(
            "inline-flex size-8 items-center justify-center rounded-full font-bold",
            band.badge,
          )}
          aria-hidden="true"
        >
          {band.icon}
        </span>
        <strong className="text-2xl">{band.label}</strong>
      </div>

      <p className="mb-4 text-lg">{triage.recommendedAction}</p>

      {isEmergency ? (
        <Alert tone="error" title="Do not wait for an appointment">
          Call <strong>999</strong> now, or go to your nearest A&amp;E. Do not drive
          yourself.
        </Alert>
      ) : (
        <div className="mb-4">
          <ButtonLink href="/appointments/book" size="lg">
            See appointments
          </ButtonLink>
        </div>
      )}

      <div className="border-t border-nhs-pale-grey pt-4 text-sm text-nhs-dark-grey">
        <p className="mb-1">
          <strong>This is not a diagnosis.</strong> It is an automated suggestion to help
          you choose an appointment, produced by{" "}
          <span className="font-mono">
            {triage.engine} {triage.engineVersion}
          </span>
          .
        </p>
        <p>
          {triage.reviewStatus === "PENDING_REVIEW"
            ? "A clinician has not yet reviewed it."
            : "A clinician has reviewed this."}
        </p>
      </div>
    </Card>
  );
}

export default function SymptomCheckPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

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
    },
  });

  const send = useMutation({
    mutationFn: (content: string) =>
      api.post<ChatTurnResponse>(`/chat/sessions/${sessionId}/messages`, { content }),
    onSuccess: (turn) => {
      queryClient.setQueryData(["chat", turn.session.id], turn);
      setDraft("");
      setSendError(null);
    },
    onError: (error) =>
      setSendError(
        error instanceof ApiError ? error.message : "We could not send that. Please try again.",
      ),
  });

  const turn = conversation.data ?? startSession.data ?? null;

  // Keep the newest message in view as the conversation grows.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [turn?.messages.length]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.trim()) send.mutate(draft.trim());
  }

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Symptom check</h1>
      <p className="mb-6 max-w-2xl text-nhs-dark-grey">
        Describe how you are feeling and we will help you find the right appointment. This
        is an automated check, not a clinician, and it does not diagnose.
      </p>

      <Alert tone="warning" title="If this is an emergency, call 999 now">
        This check cannot help in an emergency. For urgent advice call{" "}
        <strong>NHS 111</strong>.
      </Alert>

      {!turn && (
        <Card title="Start a symptom check">
          <p className="mb-4">
            We will ask a few short questions. You can stop at any time.
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
            className="mb-4 border border-nhs-mid-grey bg-[#f7f9fa] p-4"
          >
            {/* The log role announces new messages as they arrive without stealing focus
                from the input the patient is typing into. */}
            <ul role="log" aria-live="polite" aria-relevant="additions" className="flex flex-col gap-4">
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

          {turn.isClosed ? (
            <Alert
              tone={turn.session.status === "ESCALATED" ? "warning" : "info"}
              title={
                turn.session.status === "ESCALATED"
                  ? "This conversation has been passed to a member of staff"
                  : "This check is complete"
              }
            >
              {turn.session.status === "ESCALATED"
                ? "We have stopped asking questions. If you need help now, call 999."
                : "You can start another check at any time."}
            </Alert>
          ) : (
            <form onSubmit={handleSubmit} className="mb-6">
              <label htmlFor="reply" className="mb-1 block font-bold">
                Your reply
              </label>
              <div className="flex flex-wrap gap-3">
                <input
                  id="reply"
                  name="reply"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  maxLength={1000}
                  autoComplete="off"
                  disabled={send.isPending}
                  className="min-h-[44px] flex-1 border-2 border-nhs-black px-3 py-2 text-base disabled:bg-nhs-pale-grey"
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

          {turn.triage && <TriageOutcome triage={turn.triage} />}
        </>
      )}

      <p className="mt-8 text-sm text-nhs-dark-grey">
        <Link href="/dashboard">Back to your account</Link>
      </p>
    </>
  );
}
