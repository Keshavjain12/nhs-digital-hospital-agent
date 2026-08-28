/**
 * Dialog tests.
 *
 * The confirmation used to render as a card appended to the bottom of the page - far from
 * the control that opened it, and often below the fold, so the user saw nothing happen.
 *
 * jsdom does not implement the native `<dialog>` top layer, focus trap or Escape handling,
 * so these tests cover what this component adds on top of the browser: the accessible
 * name, the dismissal wiring, and - the one that matters most - that the safe action comes
 * first in a destructive dialog.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { Button, Dialog } from "@/components/ui";

beforeAll(() => {
  // jsdom implements neither, and the component calls both.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
  };
});

function ConfirmDialog({ open = true, onClose = vi.fn(), onConfirm = vi.fn() }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Cancel this appointment?"
      tone="destructive"
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Keep this appointment
          </Button>
          <Button variant="warning" onClick={onConfirm}>
            Yes, cancel it
          </Button>
        </>
      }
    >
      <p>Cancelling frees this time for someone else.</p>
    </Dialog>
  );
}

describe("Dialog", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(<ConfirmDialog />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("is exposed as a dialog named by its heading", () => {
    render(<ConfirmDialog />);

    expect(screen.getByRole("dialog", { name: /cancel this appointment/i })).toBeInTheDocument();
  });

  it("puts the safe action before the destructive one", () => {
    // Order is the mechanism: the first focusable control receives initial focus, so a
    // stray Enter must keep the appointment rather than cancel it.
    render(<ConfirmDialog />);
    const dialog = screen.getByRole("dialog");
    const buttons = within(dialog).getAllByRole("button");

    expect(buttons[0]).toHaveAccessibleName(/keep this appointment/i);
    expect(buttons[1]).toHaveAccessibleName(/yes, cancel it/i);
  });

  it("opens when asked", () => {
    render(<ConfirmDialog open />);

    expect(screen.getByRole("dialog")).toHaveAttribute("open");
  });

  it("leaves the accessibility tree when closed", () => {
    // A closed <dialog> exposes no role at all, which is what should happen: a screen
    // reader must not be able to reach a confirmation that is not being shown. Queried by
    // role rather than by attribute, so the assertion is about what assistive technology
    // can see rather than about the DOM.
    const { rerender } = render(<ConfirmDialog open />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(<ConfirmDialog open={false} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("dismisses on a backdrop click", async () => {
    // Dismissing a confirmation is the safe outcome - it keeps the appointment - so a
    // click outside cannot lose anything.
    const onClose = vi.fn();
    render(<ConfirmDialog onClose={onClose} />);

    await userEvent.click(screen.getByRole("dialog"));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not dismiss on a click inside the panel", async () => {
    const onClose = vi.fn();
    render(<ConfirmDialog onClose={onClose} />);

    await userEvent.click(screen.getByText(/frees this time/i));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("routes Escape through onClose rather than closing itself", () => {
    // The parent owns whether the dialog is open; letting the browser close it directly
    // would leave React state saying it is still open.
    const onClose = vi.fn();
    render(<ConfirmDialog onClose={onClose} />);

    screen.getByRole("dialog").dispatchEvent(new Event("cancel", { cancelable: true }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("confirms only when the destructive action is chosen", async () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(<ConfirmDialog onClose={onClose} onConfirm={onConfirm} />);

    await userEvent.click(screen.getByRole("button", { name: /keep this appointment/i }));
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /yes, cancel it/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
