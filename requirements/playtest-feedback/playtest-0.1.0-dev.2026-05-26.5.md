# Report 1 : Comet Player 1 

***

## Island Traders v0.1.0-dev — Bug & Improvement Report

### 🐛 Bugs / Defects

**1. Persistent "Connection lost. Reconnecting in 3s" loop**
- The server dropped repeatedly at end-of-season transitions (observed heavily in Year 3, Autumn). The client kept attempting reconnection but the season never advanced, leaving the game frozen at "0s" indefinitely. This appears to be a server stability issue under load at end-of-season processing.

**2. Action panel disappears after "End Turn" — no way back**
- Once "End Turn" / "Done Trading ✓" was clicked, the full action panel (Market Buy, Market Sell, Produce, etc.) became inaccessible for the rest of the season. However, Decision Hints remained visible with "Open Market Buy →" buttons that were **disabled** — meaning there was no way to act even if time remained. The action panel should remain accessible (or the End Turn should be reversible) until the timer hits zero.

**3. "Open Market Buy →" buttons in Decision Hints are non-functional**
- The buttons in the Decision Hints panel labelled "Open Market Buy →" appear clickable but do nothing (they are disabled after End Turn has been submitted). This is misleading — they should either work or be hidden/greyed out with an explanation.

**4. Produce buttons visible but non-interactive after End Turn**
- The Produce buttons in the Decision Hints section remained visible after End Turn was submitted, causing repeated confused clicks with no feedback. There was no tooltip or indication that production was locked for the rest of the season.

**5. Capital Catalogue triggered unexpectedly**
- Clicking the "Market Buy" button at certain scroll positions accidentally opened the Capital/Equipment purchase dialogue instead. This appeared to be a z-index or click-target overlap issue between panels.

**6. Bid price auto-filled with unexpected values**
- When entering quantities in the Market Buy "Place Bid" column, the price fields sometimes auto-filled with values that didn't match the reference price shown (e.g., Food showed 17.18 but the bid was calculated at 40.00/unit in the market board). The bid price input and the resulting confirmed price were inconsistent.

**7. Market bids silently failed due to insufficient capital with no pre-validation**
- Several bids were submitted and only failed at confirmation (e.g., "Bid Food failed: Mannyfact has 14.50 but bid needs 90.00"), with no real-time warning while entering quantities. The UI should show a live affordability indicator before submitting.

**8. FarmMachinery listed at 9 Dp never sold despite Agriculture having capital**
- After listing 6x FarmMachinery at 9 Dp and Comet Educator (Agriculture) gaining ~49–172 Dp in capital, no automatic matching occurred. The market board showed both an Ask (9 Dp) and a Bid (9 Dp) simultaneously but they never crossed. Possible order-matching bug.

**9. Disaster events stacked repeatedly with no cooldown**
- In a single year, the game fired: Factory Fire → Infrastructure Damage → Flood → Flood → Hospital Strike in consecutive seasons. Five consecutive production-halting events in ~5 seasons effectively eliminated any meaningful play for the Manufacturer for an entire year. There appears to be no event cooldown or cap per player/role.

**10. "Done Trading ✓" state shown even before player clicks End Turn**
- On at least one occasion the header showed "Done Trading ✓" without the player having clicked End Turn, suggesting the server may have auto-submitted the turn or the state was incorrectly synced from the server.

**11. Production capacity dropped to max 0 between seasons unexpectedly**
- After producing goods and having trained workers return, production capacity would sometimes show "max 0" the following season until manually triggered, even when all inputs (Metal, Oil, Freight) were available. The exact cause was unclear — possibly a worker assignment reset bug.

***

### 💡 Suggested Improvements

**1. End Turn should be reversible until timer hits zero**
- Players should be able to "Undo End Turn" and continue trading/producing while time remains. In board game terms this is like being able to take back a pass.

**2. Real-time capital affordability indicator in Market Buy**
- Show a running "Remaining capital after this order" counter as the player fills in quantities, preventing surprise bid failures.

**3. Clearer distinction between "Place Bid" and "Buy Now" columns**
- New players will confuse these. Column headers are small. Consider colour-coding (green = immediate, yellow = limit order) and a brief tooltip on hover.

**4. Event frequency cap / mitigation mechanic**
- Consecutive production-halting disasters are extremely punishing and feel unfair, especially for capital-intensive roles like Manufacturer. Consider: a max of 1 production-halt event per player per year, or a "disaster insurance" product.

**5. Decision Hints should link directly to the relevant action**
- The "Open Market Buy →" buttons in Decision Hints are a great idea but need to actually open the market pre-filtered to the relevant commodity. Currently they either don't work or just open the full market.

**6. "Meals runway: 0 seasons" warning should be more prominent**
- This critical warning was easy to miss. Consider a flashing red banner or a mandatory acknowledgement prompt so players don't inadvertently starve their workforce.

**7. Training request flow is too many steps**
- The training flow requires: choose profession → choose quantity → choose educator → confirm fee → confirm transport → wait for educator approval. This is 5–6 dialogue steps for a common action. Consider combining into a single form.

**8. Market Sell should offer a "List at Best Bid" one-click option**
- When a buyer is already waiting, let the seller click "Sell at best bid" without having to manually enter the price.

**9. Inventory panel should show items currently listed on market**
- Items listed for sale disappeared from the inventory panel with no indication they were on the market. A "listed" badge or separate "On Market" section would reduce confusion about actual stock levels.

**10. Player wealth leaderboard should be visible at all times**
- The "All Players" table at the bottom of the main panel is very useful but requires scrolling. A persistent compact leaderboard in the sidebar (already partially present) would help players make competitive decisions.

**11. Reconnection handling should pause the season timer**
- When the server drops, the season timer should pause server-side so players don't lose action time due to connectivity issues outside their control.

**12. Waiting room should have a visible "Start Game" button for the host**
- New players had no idea the host needed to trigger the start. The waiting room should clearly indicate who the host is and show them a prominent "Start Game" button, with other players seeing "Waiting for host to start…"

***

*Report covers v0.1.0-dev, observed during two playthroughs of game PQI3S0 and a prior game, playing the Manufacturer role as "Mannyfact" / "Comet Manufacturer".*

---

# Report 2: Comet Player 2

Island Traders — Bug & Improvement Report
Session: Room PQI3S0 | Role: Mining and Exploration (AyaySir) | Version: 0.1.0-dev.2026-05-26.5

🐛 DEFECTS
BUG-01 — "Done Trading" state auto-set at season start (Critical)
Every season began with the player already marked as "Done Trading ✓" before any actions were taken. The state should only be set by an explicit player click. Likely a server-side state carryover from the previous season not being reset.

BUG-02 — "Open Market Buy →" shortcut buttons non-functional when in "Done Trading" state (High)
Decision Hints shortcut buttons show a loading spinner and never open the form when in Done Trading state. They should be visually disabled, or automatically un-ready the player before opening the form. As-is they create a false affordance.

BUG-03 — "Market Buy" from the 📋 Menu panel unreliable (High)
Clicking "Market Buy" in the TRADE section of the action menu mostly dismissed the panel without opening the buy form. It worked reliably only in a narrow window at season start before auto-done state kicked in. Likely a race condition or focus/overlay issue.

BUG-04 — Training requests perpetually stuck at "awaiting_educator" (High)
Training requests #6–#9 (4 Mining Technicians + 1 Oil Extraction Worker) stayed at awaiting_educator from Year 1 Summer through Year 3 Autumn. Reason: "Education Island needs 1 Expertise." Expertise never appeared in the market and no mechanism existed to unblock, substitute, or cancel the requests — creating a permanent production deadlock.

BUG-05 — No way for a requester to cancel a pending training request (Medium)
Both "Reject Training Request" and "Counter Training Request" are Educator-only actions. The requester cannot withdraw a submitted request. If the Educator is inactive or resource-blocked, the requester is locked out of workforce development indefinitely.

BUG-06 — Server disconnection at end of Year 3 Autumn with no recovery (Medium)
The server dropped connection repeatedly at the 0s mark with no reconnection or final game-over/leaderboard screen. The session ended abruptly.

BUG-07 — Insurance premiums auto-purchased without player confirmation (Medium)
Life Insurance (50 Dp) and Medical Insurance (60 Dp) were issued automatically mid-session ("Policy issued" appeared in the log without a player-initiated action), spending 110 Dp without explicit consent.

BUG-08 — Multiple consecutive production-halting events with no player recourse (Low/Design)
Pandemic, Factory Fire, and Infrastructure Damage events occurred in consecutive seasons while the training pipeline was also blocked, leaving multiple seasons with zero meaningful player actions available.

💡 IMPROVEMENT SUGGESTIONS
IMP-01 — Add a "Withdraw Training Request" action for requesters
Requesters must be able to cancel their own pending training requests when the Educator is inactive or resource-blocked.

IMP-02 — Show Educator resource requirements before submitting a training request
The form should show what the Educator currently needs (e.g. "Chromio requires 1 Expertise — currently unavailable") so the player can make an informed decision upfront.

IMP-03 — Allow the requester to supply the Educator's missing resources
If Expertise is needed but unavailable, the requester should be able to source and supply it themselves, breaking the deadlock and creating interesting market dynamics.

IMP-04 — Decision Hints shortcut buttons should auto-undo "Done Trading"
Clicking "Open Market Buy →" or "Request Training →" from hints should automatically undo Done Trading state and open the relevant form, or prompt the player to confirm.

IMP-05 — "Done Trading" must never be auto-set by the server
Only a deliberate player click should set this state. Auto-setting it at season start is both a bug and a poor UX experience.

IMP-06 — Production Capacity panel should show the specific blocking reason inline
"max 0" with no explanation forces players to hunt through Decision Hints. It should show "Blocked: no active Technicians" or "Blocked: missing 0.05 Oil input" directly in the panel.

IMP-07 — Add public Education Island capacity visibility
Players have no way to see how many training slots are available at Chromio's island or what resources are currently blocking approvals without submitting a request and getting an error response.

IMP-08 — Add an emergency Food purchase mechanism
With no active Agriculture player, AyaySir ran at 0 meals for the majority of the game with no recourse. An emergency food option (e.g. buy from the bank at a penalty price) would prevent total starvation deadlocks.

IMP-09 — Add a final game-over screen with full statistics
The game should display a winner announcement, final leaderboard, and per-player production/trade summary when it ends. The abrupt disconnection provided no closure or learning value.

IMP-10 — Cap consecutive production-halting random events
Multiple halt events (Pandemic, Factory Fire) in back-to-back seasons combined with a blocked training pipeline left no viable gameplay for extended periods. Consider a cooldown between halt events.

---

# Report 3 : Codex Player

From the Banking POV, the main experience was: I could join, bid 200 for Banking, invest, sell insurance, issue loans, and generally operate the role through the UI. The flow worked well enough for a real multiplayer POC, but several defects showed up.

**Defects / Friction**

- Season rollover often left the header or action state stale until refresh. I saw Spring/Summer/Autumn mismatches and “Done Trading” carrying into the next season.

- Loan rollover was confusing or broken. A loan showing “matures in 1 season” still produced “No active loans to roll over,” and an earlier mature loan defaulted before I could intervene.

- The app let Banking accept a loan on behalf of the borrower. Useful for testing, but in multiplayer that is a consent/authority bug.

- Insurance UI showed “None” even after policies had been sold; policies were only visible through logs/manage actions.

- Banking production showed big positive events like Bull Market, but production remained blocked by inputs with weak explanation. The capacity panel said “InsurancePolicies underwrite up to 0,” yet Sell Insurance still opened.

- Training dependencies got stuck around Expertise. Education could not approve requests, including my Banker training, and the UI did not make the system-wide bottleneck very actionable.

- Market and hint behavior was uneven. “Meals runway: 0” told me to buy food, but there was no ask, only bids. The hint remained prominent even after I posted a food bid.

- The game log became noisy and hard to scan, especially when old history dominated the page. Recent events were findable, but not comfortable.

- Websocket reconnect loop repeated “Connection lost. Reconnecting in 3s…” many times. A refresh recovered the shell, but lost the room attachment and dropped me to the landing page.

**Banking Balance Notes**

- Banking had cash but was input-starved and couldn’t meaningfully produce without Expertise/input supply.

- The Comet loan default hit hard: Banking paid external depositors while only partially recovering from borrower cash.

- Refinancing created new loans beyond the original game horizon, raising a scoring question: if the game ends before those mature, are unmatured loan assets/liabilities fairly valued?

Overall: the Bank role is playable and interesting, but the biggest defects are rollover/state sync, borrower consent, loan maturity timing, and unclear visibility around insurance/training/input constraints.

# Report 4: Personal Feedback (Real Human)

1. Ran out of workers and unable to continue to produce (roadblock).  It’s easy to create a larger starting base, but that would just kick the can down the road.  I would suggest being able to hire workers for a fee for a given number of seasons from other Islands where they might be underutilised, and the island is strapped for cash.  For example I would like to hire 2 workers for 2 seasons for 100 Dp including the 2 Passenger seats required.
2. Unused Cash Balances: It would be great if players can place cash on deposit for a given term (1-3 years) with the bank at a rate comparable to the cost of funds rate.  This would introduce the concept of deposits with the bank.
3. (See 2 above) If a player defaults on a lease, there will be a 10Dp penalty and the payment will be withdrawn from any funds they have on deposit.
4. Given that all players were constrained by Food towards the later stages of the game, it might be prudent to reduce the amount of Food required to feed the population. Suggest 50% of current need.

