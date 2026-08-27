/**
 * Design system accessibility tests.
 *
 * These assert the guarantees the components exist to provide. Requirement C5 makes
 * WCAG 2.1 AA a legal obligation, and the project plan puts an accessibility audit in
 * Sprint 4 - by which point retrofitting is expensive. Testing the primitives now is what
 * keeps that audit from becoming a rewrite.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { Alert, Button, ErrorSummary, TextInput } from "@/components/ui";

describe("Button", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(<Button>Book appointment</Button>);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("defaults to type=button so it cannot submit a form by accident", () => {
    render(<Button>Cancel</Button>);

    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("blocks repeat clicks while loading", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Confirm booking
      </Button>,
    );

    await userEvent.click(screen.getByRole("button"));

    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("announces the busy state without changing its accessible name", () => {
    render(<Button loading loadingText="Signing in">Sign in</Button>);

    const button = screen.getByRole("button", { name: /sign in/i });

    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("meets the 44px minimum target size", () => {
    render(<Button>Continue</Button>);

    expect(screen.getByRole("button").className).toContain("min-h-[44px]");
  });
});

describe("TextInput", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <TextInput label="NHS number" hint="It is on any NHS letter" required />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("associates the label with the input", () => {
    render(<TextInput label="Email address" />);

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it("exposes hint and error together via aria-describedby", () => {
    render(
      <TextInput label="NHS number" hint="10 digits" error="Enter a valid NHS number" />,
    );

    const input = screen.getByLabelText(/nhs number/i);
    const describedBy = input.getAttribute("aria-describedby")?.split(" ") ?? [];

    expect(describedBy).toHaveLength(2);
    expect(input).toHaveAttribute("aria-invalid", "true");

    const described = describedBy
      .map((id) => document.getElementById(id)?.textContent ?? "")
      .join(" ");
    expect(described).toContain("10 digits");
    expect(described).toContain("Enter a valid NHS number");
  });

  it("states errors in text, not colour alone", () => {
    render(<TextInput label="Password" error="Too short" />);

    // WCAG 1.4.1: a red border conveys nothing to a screen reader or a colour-blind user.
    expect(screen.getByText(/error:/i)).toBeInTheDocument();
  });

  it("marks optional fields explicitly rather than leaving them unlabelled", () => {
    render(<TextInput label="NHS number" />);

    expect(screen.getByText(/optional/i)).toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <Alert tone="error" title="There is a problem">
        Check your answers
      </Alert>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("interrupts with role=alert for errors", () => {
    render(<Alert tone="error">Booking failed</Alert>);

    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });

  it("waits its turn for non-errors", () => {
    render(<Alert tone="success">Appointment booked</Alert>);

    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("names the tone in text so it is not carried by colour alone", () => {
    render(<Alert tone="warning">Check this</Alert>);

    expect(screen.getByText(/important:/i)).toBeInTheDocument();
  });
});

describe("ErrorSummary", () => {
  it("renders nothing when there are no errors", () => {
    const { container } = render(<ErrorSummary errors={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("takes focus so the problem is announced immediately after submit", () => {
    render(<ErrorSummary errors={[{ field: "email", message: "Enter your email" }]} />);

    expect(screen.getByRole("alert")).toHaveFocus();
  });

  it("links each error to the field that caused it", async () => {
    render(
      <>
        <ErrorSummary errors={[{ field: "email", message: "Enter your email address" }]} />
        <TextInput label="Email address" name="email" />
      </>,
    );

    await userEvent.click(screen.getByRole("link", { name: /enter your email address/i }));

    // Keyboard and magnifier users must be able to jump straight to the problem rather
    // than hunting for it down a long form.
    expect(screen.getByLabelText(/email address/i)).toHaveFocus();
  });
});
