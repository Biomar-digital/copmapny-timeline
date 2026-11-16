// Markets a document can belong to and an account can be limited to.
// Keep in sync with MARKETS in worker/index.js and policy-formatter/tools/publish.py.
// The Worker is what enforces access; this list only drives the pickers.
window.MARKETS = ["Australia", "Chile", "China", "Costa Rica", "Denmark", "Ecuador", "Spain",
  "Greece", "Iceland", "Norway", "United Kingdom (Scotland)", "Turkey", "Vietnam"];
window.GLOBAL_MARKET = "Global";      // group-wide documents (everything that existed before markets)
window.ALL_MARKETS = "*";             // sign-up token: "full access" — the approver decides
