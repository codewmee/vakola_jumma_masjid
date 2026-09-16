(function () {
  "use strict";

  const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || "";

  // ---------- Live clock ----------
  function startClock() {
    const el = document.getElementById("live-clock");
    if (!el) return;
    const tick = () => {
      el.textContent = new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    };
    tick();
    setInterval(tick, 1000);
  }

  // ---------- Toast ----------
  function showToast(message, isError) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("is-error", !!isError);
    toast.classList.add("is-visible");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("is-visible"), 5000);
  }

  // ---------- Modals ----------
  function initModals() {
    const overlays = document.querySelectorAll(".modal-overlay");

    document.querySelectorAll("[data-open-modal]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const name = trigger.getAttribute("data-open-modal");
        const overlay = document.getElementById(`modal-${name}`);
        if (overlay) overlay.classList.add("is-open");
      });
    });

    overlays.forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.classList.remove("is-open");
      });
      overlay.querySelectorAll("[data-close-modal]").forEach((btn) => {
        btn.addEventListener("click", () => overlay.classList.remove("is-open"));
      });
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        overlays.forEach((o) => o.classList.remove("is-open"));
      }
    });
  }

  // ---------- Form helpers ----------
  function clearFieldErrors(form) {
    form.querySelectorAll(".field-error").forEach((el) => {
      el.textContent = "";
      el.classList.remove("is-visible");
    });
  }

  function showFieldError(form, field, message) {
    const el = form.querySelector(`[data-error-for="${field}"]`);
    if (el) {
      el.textContent = message;
      el.classList.add("is-visible");
    }
  }

  async function postJSON(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_e) {
      data = { ok: false, error: "Unexpected server response." };
    }
    return { status: res.status, data };
  }

  function setSubmitting(form, isSubmitting) {
    const btn = form.querySelector('button[type="submit"]');
    if (!btn) return;
    btn.disabled = isSubmitting;
    btn.dataset.originalText = btn.dataset.originalText || btn.textContent;
    btn.textContent = isSubmitting ? "Submitting…" : btn.dataset.originalText;
  }

  // ---------- Nikah + Madrasa forms (simple submit-and-close) ----------
  function initSimpleForm(formId, endpoint) {
    const form = document.getElementById(formId);
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearFieldErrors(form);
      setSubmitting(form, true);

      const payload = Object.fromEntries(new FormData(form).entries());
      const { status, data } = await postJSON(endpoint, payload);

      setSubmitting(form, false);

      if (data.ok) {
        showToast(data.message || "Submitted successfully.", false);
        form.reset();
        form.closest(".modal-overlay")?.classList.remove("is-open");
      } else if (status === 400 && data.field) {
        showFieldError(form, data.field, data.error);
      } else {
        showToast(data.error || "Something went wrong. Please try again.", true);
      }
    });
  }

  // ---------- Donation form ----------
  function initDonationForm() {
    const form = document.getElementById("form-donation");
    if (!form) return;

    const amountButtons = form.querySelectorAll(".donation-amount-btn");
    const customWrap = document.getElementById("donation-custom-amount");
    const customInput = document.getElementById("donation-amount");
    const submitBtn = document.getElementById("donation-submit");
    const successView = document.getElementById("donation-success");
    const successMsg = document.getElementById("donation-success-message");

    let selectedAmount = null;

    function selectAmount(btn) {
      amountButtons.forEach((b) => b.classList.remove("border-gold-600", "text-gold-600"));
      btn.classList.add("border-gold-600", "text-gold-600");

      const raw = btn.getAttribute("data-amount");
      if (raw === "other") {
        customWrap.classList.remove("hidden");
        customInput.focus();
        selectedAmount = null;
        submitBtn.disabled = true;
      } else {
        customWrap.classList.add("hidden");
        selectedAmount = Number(raw);
        submitBtn.disabled = false;
      }
    }

    amountButtons.forEach((btn) => btn.addEventListener("click", () => selectAmount(btn)));

    customInput?.addEventListener("input", () => {
      const val = Number(customInput.value);
      selectedAmount = val > 0 ? val : null;
      submitBtn.disabled = !selectedAmount;
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearFieldErrors(form);

      if (!selectedAmount || selectedAmount < 1) {
        showFieldError(form, "amount", "Please choose or enter an amount.");
        return;
      }

      setSubmitting(form, true);
      const { status, data } = await postJSON("/api/donate", { amount: selectedAmount });
      setSubmitting(form, false);

      if (!data.ok) {
        if (status === 400 && data.field) {
          showFieldError(form, data.field, data.error);
        } else {
          showToast(data.error || "Could not process donation. Please try again.", true);
        }
        return;
      }

      if (data.mode === "razorpay" && window.Razorpay) {
        const rzp = new window.Razorpay({
          key: data.key_id,
          amount: data.amount,
          currency: data.currency,
          order_id: data.order_id,
          name: window.__SITE__.mosqueName,
          description: "Sadaqah / Donation",
          theme: { color: "#9a6e22" },
          handler: async function (response) {
            const verify = await postJSON("/api/donate/verify", {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            if (verify.data.ok) {
              showDonationSuccess(verify.data.message);
            } else {
              showToast(verify.data.error || "Payment verification failed.", true);
            }
          },
          modal: {
            ondismiss: function () {
              showToast("Payment cancelled.", true);
            },
          },
        });
        rzp.open();
      } else {
        showDonationSuccess(data.message);
      }
    });

    function showDonationSuccess(message) {
      form.classList.add("hidden");
      successView.classList.remove("hidden");
      if (message) successMsg.textContent = message;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    startClock();
    initModals();
    initSimpleForm("form-nikah", "/api/nikah");
    initSimpleForm("form-madrasa", "/api/madrasa");
    initDonationForm();
  });
})();
