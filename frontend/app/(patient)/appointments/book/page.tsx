"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Alert, Button, Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api, ApiError } from "@/lib/api";
import type { BookingCreatedResponse, HoldResponse, SlotItem, SlotListResponse } from "@/types/api";

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

export default function BookAppointmentPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [department, setDepartment] = useState("");
  const [chosen, setChosen] = useState<SlotItem | null>(null);
  const [holdExpiry, setHoldExpiry] = useState<Date | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [conflict, setConflict] = useState<string | null>(null);

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
      api.post<BookingCreatedResponse>("/appointments", { slotId: slot.id }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["appointments"] });
      router.replace(`/appointments?booked=${result.appointment.reference}`);
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
        <Link href="/appointments">Back to your appointments</Link>
      </p>

      <h1 className="mb-2 text-4xl font-bold">Book an appointment</h1>
      <p className="mb-6 text-nhs-dark-grey">
        Choose a time that suits you. We hold it for five minutes while you confirm.
      </p>

      {conflict && (
        <Alert tone="warning" title="Please choose another time" focusOnMount>
          {conflict}
        </Alert>
      )}

      <div className="mb-6">
        <label htmlFor="department" className="mb-1 block text-base font-bold">
          Department
          <span className="ml-1 font-normal text-nhs-dark-grey">(optional)</span>
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
          <option value="">All departments</option>
          {departments.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {slots.isPending && (
        <p role="status" aria-live="polite">
          Loading available times…
        </p>
      )}

      {slots.error && (
        <Alert tone="error" title="Could not load available times" focusOnMount>
          {slots.error.message}
        </Alert>
      )}

      {slots.data && days.length === 0 && (
        <Alert tone="info" title="No appointments available">
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
                      {selected ? "Held for you" : slot.departmentName}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {chosen && holdExpiry && (
        <Card title="Confirm your appointment" className="sticky bottom-4 border-2 border-nhs-black">
          <dl className="mb-4 grid gap-3 sm:grid-cols-3">
            <div>
              <dt className="font-bold">When</dt>
              <dd>
                {dayFormat.format(new Date(chosen.startsAt))},{" "}
                {timeFormat.format(new Date(chosen.startsAt))}
              </dd>
            </div>
            <div>
              <dt className="font-bold">Department</dt>
              <dd>{chosen.departmentName}</dd>
            </div>
            <div>
              <dt className="font-bold">Clinician</dt>
              <dd>{chosen.clinicianName ?? "To be confirmed"}</dd>
            </div>
          </dl>

          <p className="mb-4" role="status" aria-live="polite">
            We are holding this time for{" "}
            <strong>
              {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
            </strong>
            . If someone books it first we will tell you and nothing will be booked.
          </p>

          <div className="flex flex-wrap gap-3">
            <Button
              size="lg"
              loading={book.isPending}
              loadingText="Booking your appointment"
              onClick={() => book.mutate(chosen)}
            >
              Confirm this appointment
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => {
                setChosen(null);
                setHoldExpiry(null);
              }}
            >
              Choose a different time
            </Button>
          </div>
        </Card>
      )}
    </>
  );
}
