"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Alert, Button, Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import { UK_TIME_ZONE, ukDayKey } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type {
  AppointmentDetailResponse,
  BookingCreatedResponse,
  DepartmentListResponse,
  HoldResponse,
  SlotItem,
  SlotListResponse,
} from "@/types/api";

/**
 * Group slots by UK calendar day so the picker reads like a diary, not a flat list.
 *
 * Keyed on the day in Europe/London rather than the viewer's device. The previous version
 * used toDateString(), which groups by whatever zone the browser happens to be in, so a
 * late slot could appear under the wrong day for anyone outside the UK.
 */
function byDay(slots: readonly SlotItem[]): Array<[string, SlotItem[]]> {
  const days = new Map<string, SlotItem[]>();
  for (const slot of slots) {
    const key = ukDayKey(slot.startsAt);
    const bucket = days.get(key);
    if (bucket) bucket.push(slot);
    else days.set(key, [slot]);
  }
  return [...days.entries()];
}

// Hospital time, always - see lib/format.ts for why the device's own zone is never used.
const timeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
});
const dayFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
});

/**
 * One department's times across several clinic days. The API caps a request at 200.
 *
 * The page used to load times for every department at once. With six departments the first
 * request was used up entirely by the next single day, so a patient could not see or choose
 * any later date without first discovering the department filter.
 */
const SLOT_LIMIT = "200";

function BookAppointmentForm() {
  const router = useRouter();
  const params = useSearchParams();

  // Rescheduling is the same picker with different framing and a different endpoint, not a
  // second screen. Keeping one screen means the slot-holding, countdown and conflict
  // handling cannot drift apart between the two paths.
  const rescheduleId = params.get("reschedule");
  const queryClient = useQueryClient();
  const t = useT();

  const [chosenDepartment, setChosenDepartment] = useState("");
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

  // The full list, from its own endpoint. Deriving it from the loaded slots meant choosing
  // one department shrank the list to just that one.
  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentListResponse>("/departments"),
    staleTime: 5 * 60_000,
  });

  // When moving an appointment, start in the department it is already in. Derived rather
  // than set in an effect, so the patient's own choice always wins once they make one.
  const movingDepartment = useMemo(() => {
    const name = moving.data?.appointment.departmentName;
    if (!name) return "";
    return departments.data?.items.find((item) => item.name === name)?.id ?? "";
  }, [moving.data, departments.data]);

  const department = chosenDepartment || movingDepartment;

  const slots = useQuery({
    queryKey: ["slots", department],
    queryFn: () =>
      api.get<SlotListResponse>(
        `/slots?${new URLSearchParams({ limit: SLOT_LIMIT, departmentId: department })}`,
      ),
    enabled: Boolean(department),
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
            setChosenDepartment(event.target.value);
            setChosen(null);
            setHoldExpiry(null);
          }}
          className="block min-h-[44px] w-full max-w-md border-2 border-nhs-black bg-white px-3 py-2 text-base"
        >
          <option value="">{t("booking.chooseDepartmentOption")}</option>
          {(departments.data?.items ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>

      {departments.error && (
        <Alert tone="error" title={t("common.somethingWentWrong")} focusOnMount>
          {departments.error.message}
        </Alert>
      )}

      {!department && departments.data && (
        <p className="mb-6">{t("booking.chooseDepartment")}</p>
      )}

      {/* isLoading, not isPending: a query waiting for a department to be chosen is
          "pending" too, and would otherwise announce it is loading times it has not been
          asked for. */}
      {slots.isLoading && (
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
          <h2 className="mb-3 text-2xl font-bold">
            {dayFormat.format(new Date(daySlots[0].startsAt))}
          </h2>
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
                    {/* The department is already chosen, so name the clinician instead. */}
                    {(selected || slot.clinicianName) && (
                      <span className="block text-xs font-normal">
                        {selected ? t("booking.held") : slot.clinicianName}
                      </span>
                    )}
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
