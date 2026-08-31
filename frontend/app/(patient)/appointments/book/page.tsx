"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Alert, Button, Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type {
  AppointmentDetailResponse,
  BookingCreatedResponse,
  HoldResponse,
  SlotItem,
  SlotListResponse,
} from "@/types/api";

/** Group slots by calendar day so the picker reads like a diary, not a flat list. */
function byDay(slots: readonly SlotItem[]): Array<[string, SlotItem[]]> {
  const days = new Map<string, SlotItem[]>();
  for (const slot of slots) {
    const key = new Date(slot.startsAt).toDateString();
    const bucket = days.get(key);
    if (bucket) bucket.push(slot);
    else days.set(key, [slot]);
  }
  return [...days.entries()];
}

const timeFormat = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const dayFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

function BookAppointmentForm() {
  const router = useRouter();
  const params = useSearchParams();

  // Rescheduling is the same picker with different framing and a different endpoint, not a
  // second screen. Keeping one screen means the slot-holding, countdown and conflict
  // handling cannot drift apart between the two paths.
  const rescheduleId = params.get("reschedule");
  const queryClient = useQueryClient();
  const t = useT();

  const [department, setDepartment] = useState("");
  const [chosen, setChosen] = useState<SlotItem | null>(null);
  const [holdExpiry, setHoldExpiry] = useState<Date | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [conflict, setConflict] = useState<string | null>(null);

  // Fetched so the page can name the appointment being moved. Without it the patient is
  // asked to pick a new time with no reminder of what they are changing.
  const moving = useQuery({
    queryKey: ["appointment", rescheduleId],
    queryFn: () => api.get<AppointmentDetailResponse>(`/appointments/${rescheduleId}`),
    enabled: Boolean(rescheduleId),
    retry: false,
  });

  const slots = useQuery({
    queryKey: ["slots", department],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "120" });
      if (department) params.set("departmentId", department);
      return api.get<SlotListResponse>(`/slots?${params}`);
    },
  });

  const hold = useMutation({
    mutationFn: (slot: SlotItem) => api.post<HoldResponse>(`/slots/${slot.id}/hold`),
    onSuccess: (result, slot) => {
      setChosen(slot);
      setHoldExpiry(new Date(result.expiresAt));
      setConflict(null);
    },
    onError: (error) => {
      setChosen(null);
      setHoldExpiry(null);
      setConflict(
        error instanceof ApiError
          ? error.message
          : "We could not reserve that time. Please try another.",
      );
      void slots.refetch();
    },
  });

  const book = useMutation({
    mutationFn: (slot: SlotItem) =>
      rescheduleId
        ? api.post<BookingCreatedResponse>(`/appointments/${rescheduleId}/reschedule`, {
            newSlotId: slot.id,
          })
        : api.post<BookingCreatedResponse>("/appointments", { slotId: slot.id }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["appointments"] });
      // The banner is chosen from what the server says it did, not from what this page
      // asked for. If the two ever disagree, the patient should be told the truth.
      const outcome = result.kind === "rescheduled" ? "rescheduled" : "booked";
      router.replace(`/appointments?${outcome}=${result.appointment.reference}`);
    },
    onError: (error) => {
      setChosen(null);
      setHoldExpiry(null);
      // The backend distinguishes "someone took it" from "your hold lapsed". Both mean
      // choose again, but only one implies the slot is actually gone, so the wording
      // comes from the API rather than being guessed here.
      setConflict(
        error instanceof ApiError
          ? error.message
          : "We could not book that time. Please try another.",
      );
      void slots.refetch();
    },
  });

  // Countdown driven from the server's expiry timestamp.
  useEffect(() => {
    if (!holdExpiry) return;
    const tick = () => {
      const remaining = Math.max(0, Math.round((holdExpiry.getTime() - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining === 0) {
        setChosen(null);
        setHoldExpiry(null);
        setConflict("Your reserved time expired. Please choose again.");
        void slots.refetch();
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [holdExpiry, slots]);

  const departments = useMemo(() => {
    const seen = new Map<string, string>();
    for (const slot of slots.data?.items ?? []) seen.set(slot.departmentId, slot.departmentName);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [slots.data]);

  const days = byDay(slots.data?.items ?? []);

  return (
    <>
      <p className="mb-4">
        <Link href="/appointments">{t("booking.backToAppointments")}</Link>
      </p>

      <h1 className="mb-2 text-4xl font-bold">
        {t(rescheduleId ? "booking.reschedule.title" : "booking.title")}
      </h1>
      <p className="mb-6 text-nhs-dark-grey">
        {t(rescheduleId ? "booking.reschedule.intro" : "booking.intro")}
      </p>

      {/* Names the appointment being moved, so the patient can see they are changing the
          one they meant. Rendered only once loaded - a half-written sentence with a
          missing date would be worse than waiting. */}
      {rescheduleId && moving.data && (
        <Alert tone="info" title={t("booking.reschedule.movingTitle")}>
          {t("booking.reschedule.moving", {
            when: `${dayFormat.format(new Date(moving.data.appointment.startsAt))}, ${timeFormat.format(
              new Date(moving.data.appointment.startsAt),
            )}`,
          })}
        </Alert>
      )}

      {rescheduleId && moving.isError && (
        <Alert tone="warning" title={t("booking.conflict.title")}>
          {t("booking.reschedule.notFound")}
        </Alert>
      )}

      {conflict && (
        <Alert tone="warning" title={t("booking.conflict.title")} focusOnMount>
          {conflict}
        </Alert>
      )}

      <div className="mb-6">
        <label htmlFor="department" className="mb-1 block text-base font-bold">
          {t("booking.department")}
        </label>
        <select
          id="department"
          value={department}
          onChange={(event) => {
            setDepartment(event.target.value);
            setChosen(null);
            setHoldExpiry(null);
          }}
          className="block min-h-[44px] w-full max-w-md border-2 border-nhs-black bg-white px-3 py-2 text-base"
        >
          <option value="">{t("booking.allDepartments")}</option>
          {departments.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {slots.isPending && (
        <p role="status" aria-live="polite">
          {t("booking.loadingTimes")}
        </p>
      )}

      {slots.error && (
        <Alert tone="error" title={t("common.somethingWentWrong")} focusOnMount>
          {slots.error.message}
        </Alert>
      )}

      {slots.data && days.length === 0 && (
        <Alert tone="info" title={t("booking.none.title")}>
          There are no free times in this department at the moment. Try another department,
          or contact the hospital directly.
        </Alert>
      )}

      {days.map(([day, daySlots]) => (
        <section key={day} className="mb-8">
          <h2 className="mb-3 text-2xl font-bold">{dayFormat.format(new Date(day))}</h2>
          <ul className="flex flex-wrap gap-3">
            {daySlots.map((slot) => {
              const selected = chosen?.id === slot.id;
              return (
                <li key={slot.id}>
                  <button
                    type="button"
                    onClick={() => hold.mutate(slot)}
                    disabled={hold.isPending || book.isPending}
                    // aria-pressed rather than colour alone: a screen reader user must be
                    // able to tell which time is currently held.
                    aria-pressed={selected}
                    className={cn(
                      "min-h-[44px] min-w-[92px] border-2 px-3 py-2 font-bold",
                      selected
                        ? "border-nhs-green bg-nhs-green text-white"
                        : "border-nhs-black bg-white hover:bg-nhs-pale-grey",
                      "disabled:cursor-not-allowed disabled:opacity-60",
                    )}
                  >
                    <span className="block">{timeFormat.format(new Date(slot.startsAt))}</span>
                    <span className="block text-xs font-normal">
                      {selected ? t("booking.held") : slot.departmentName}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {chosen && holdExpiry && (
        <Card
          title={t("booking.confirm.title")}
          className="sticky bottom-4 border-2 border-nhs-black"
        >
          <dl className="mb-4 grid gap-3 sm:grid-cols-3">
            <div>
              <dt className="font-bold">{t("booking.confirm.when")}</dt>
              <dd>
                {dayFormat.format(new Date(chosen.startsAt))},{" "}
                {timeFormat.format(new Date(chosen.startsAt))}
              </dd>
            </div>
            <div>
              <dt className="font-bold">{t("booking.confirm.department")}</dt>
              <dd>{chosen.departmentName}</dd>
            </div>
            <div>
              <dt className="font-bold">{t("booking.confirm.clinician")}</dt>
              <dd>{chosen.clinicianName ?? t("booking.confirm.toBeConfirmed")}</dd>
            </div>
          </dl>

          <p className="mb-4" role="status" aria-live="polite">
            {t("booking.confirm.holding", {
              countdown: `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`,
            })}
          </p>

          <div className="flex flex-wrap gap-3">
            <Button
              size="lg"
              loading={book.isPending}
              loadingText={t(
                rescheduleId ? "booking.reschedule.working" : "booking.confirm.booking",
              )}
              onClick={() => book.mutate(chosen)}
            >
              {t(rescheduleId ? "booking.reschedule.action" : "booking.confirm.action")}
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => {
                setChosen(null);
                setHoldExpiry(null);
              }}
            >
              {t("booking.confirm.chooseAnother")}
            </Button>
          </div>
        </Card>
      )}
    </>
  );
}

export default function BookAppointmentPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <BookAppointmentForm />
    </Suspense>
  );
}
