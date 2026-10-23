// Interactive Loan EMI Calculator

function formatINR(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  const num = Math.round(Number(val) * 100) / 100;
  const parts = Math.abs(num).toFixed(2).split(".");
  let intPart = parts[0];
  const decPart = parts[1];
  const isNegative = num < 0;

  if (intPart.length > 3) {
    const lastThree = intPart.substring(intPart.length - 3);
    const otherNumbers = intPart.substring(0, intPart.length - 3);
    const pairs = [];
    let rem = otherNumbers;
    while (rem.length > 0) {
      if (rem.length > 2) {
        pairs.unshift(rem.substring(rem.length - 2));
        rem = rem.substring(0, rem.length - 2);
      } else {
        pairs.unshift(rem);
        rem = "";
      }
    }
    intPart = pairs.join(",") + "," + lastThree;
  }
  return (isNegative ? "-₹" : "₹") + intPart + "." + decPart;
}

function calculateLoanEMI(amount, annualRate, tenureMonths) {
  if (amount <= 0 || tenureMonths <= 0) return { emi: 0, totalInterest: 0, totalPayment: 0 };
  const monthlyRate = annualRate / 100.0 / 12.0;
  if (monthlyRate === 0) {
    const emi = amount / tenureMonths;
    return { emi, totalInterest: 0, totalPayment: amount };
  }
  const factor = Math.pow(1 + monthlyRate, tenureMonths);
  const emi = (amount * monthlyRate * factor) / (factor - 1);
  const totalPayment = emi * tenureMonths;
  const totalInterest = totalPayment - amount;
  return { emi, totalInterest, totalPayment };
}

function updateCalculatorDisplay() {
  const amountInput = document.getElementById("calc-amount");
  const rateInput = document.getElementById("calc-rate");
  const tenureInput = document.getElementById("calc-tenure");

  if (!amountInput || !rateInput || !tenureInput) return;

  const amount = parseFloat(amountInput.value) || 0;
  const rate = parseFloat(rateInput.value) || 0;
  const tenure = parseInt(tenureInput.value, 10) || 0;

  const result = calculateLoanEMI(amount, rate, tenure);

  const emiEl = document.getElementById("calc-emi-val");
  const interestEl = document.getElementById("calc-interest-val");
  const paymentEl = document.getElementById("calc-payment-val");
  const principalEl = document.getElementById("calc-principal-val");
  const rateVal = document.getElementById("calc-rate-val");
  const tenureVal = document.getElementById("calc-tenure-val");

  if (rateVal) rateVal.textContent = rate + "%";
  if (tenureVal) tenureVal.textContent = tenure + " Mos";
  if (emiEl) emiEl.textContent = formatINR(result.emi);
  if (interestEl) interestEl.textContent = formatINR(result.totalInterest);
  if (paymentEl) paymentEl.textContent = formatINR(result.totalPayment);
  if (principalEl) principalEl.textContent = formatINR(amount);

  // Update visual distribution bar
  const principalBar = document.getElementById("calc-bar-principal");
  const interestBar = document.getElementById("calc-bar-interest");
  if (principalBar && interestBar && result.totalPayment > 0) {
    const principalPct = (amount / result.totalPayment) * 100;
    const interestPct = (result.totalInterest / result.totalPayment) * 100;
    principalBar.style.width = principalPct + "%";
    interestBar.style.width = interestPct + "%";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const amountSlider = document.getElementById("calc-amount");
  const rateSlider = document.getElementById("calc-rate");
  const tenureSlider = document.getElementById("calc-tenure");

  [amountSlider, rateSlider, tenureSlider].forEach((el) => {
    if (el) {
      el.addEventListener("input", updateCalculatorDisplay);
    }
  });

  // Product selector sync
  const productSelect = document.getElementById("calc-product-select");
  if (productSelect) {
    const applyProductPreset = () => {
      const selectedOption = productSelect.selectedOptions[0];
      if (selectedOption && selectedOption.value) {
        const rate = selectedOption.getAttribute("data-rate");
        const minAmt = selectedOption.getAttribute("data-min");
        const maxAmt = selectedOption.getAttribute("data-max");
        const minTenure = selectedOption.getAttribute("data-min-tenure");
        const maxTenure = selectedOption.getAttribute("data-max-tenure");

        if (rate && rateSlider) rateSlider.value = rate;
        if (minAmt && amountSlider) {
          amountSlider.min = minAmt;
          if (parseFloat(amountSlider.value) < parseFloat(minAmt)) amountSlider.value = minAmt;
        }
        if (maxAmt && amountSlider) {
          amountSlider.max = maxAmt;
          if (parseFloat(amountSlider.value) > parseFloat(maxAmt)) amountSlider.value = maxAmt;
        }
        if (minTenure && tenureSlider) {
          tenureSlider.min = minTenure;
          if (parseInt(tenureSlider.value, 10) < parseInt(minTenure, 10)) tenureSlider.value = minTenure;
        }
        if (maxTenure && tenureSlider) {
          tenureSlider.max = maxTenure;
          if (parseInt(tenureSlider.value, 10) > parseInt(maxTenure, 10)) tenureSlider.value = maxTenure;
        }

        updateCalculatorDisplay();
      }
    };

    productSelect.addEventListener("change", applyProductPreset);
    if (productSelect.value) {
      applyProductPreset();
    }
  }

  updateCalculatorDisplay();
});
