# Northstar Analytics Inc.

**Frozen as benchmark v0.1.** This document is the ground truth a judge may rely
on. If a case contradicts it, the case is wrong.

## What the company is

Northstar Analytics Inc. is a B2B SaaS company selling a product-analytics
platform on annual and multi-year contracts. Delaware C-corp, US-only operations,
accrual basis, calendar fiscal year. Around 90 employees. Revenue run rate roughly
$24M. Series B, audited annually, not public.

The finance team is four people: a Controller, two staff accountants, and a
part-time CFO. They close the books monthly, on a five-business-day close.

## Why automation matters here

The two staff accountants spend most of a close on three things: matching cash
receipts to open invoices, coding vendor invoices, and explaining budget variances.
The volumes are high and the individual amounts are small, but an error that
reaches the financial statements is expensive to unwind and embarrassing with the
audit committee.

So the question is not "can a model do accounting". It is: **how much of this can
be done without a person, while keeping wrong automatic actions rare enough that
the Controller is willing to stop looking at each one.**

## Period being closed

All cases are in the **September 2026** close unless the case says otherwise. The
cutoff is **2026-09-30**. Anything dated after that belongs to October.

## Fiscal calendar

- fiscal year: calendar year, 2026
- period being closed: 2026-09
- cutoff date: 2026-09-30
- prior period: 2026-08, closed and locked
- audit: annual, by an external firm, for the year ending 2026-12-31

## Who may approve what

| Amount | Approval required |
|---|---|
| under $1,000 | staff accountant, no second signature |
| $1,000 to $10,000 | Controller |
| over $10,000 | Controller and CFO |
| any capitalized asset | Controller, regardless of amount |
| any journal entry to a closed period | Controller and CFO |

"Requires human review" in the labels means *this company's policy requires a
person*, not that the case is difficult.

## Vendors

| Vendor | What they bill for | Normal cadence |
|---|---|---|
| Cloudspan | infrastructure hosting | monthly, varies with usage |
| Brightline Legal | outside counsel | monthly, irregular amounts |
| Figma | design seats | monthly, fixed |
| AWS | compute and storage | monthly, varies with usage |
| Meridian Staffing | contract engineers | monthly, per timesheet |
| Harbor Insurance | D&O and general liability | annual, paid upfront |
| Deskworks | office furniture and equipment | occasional, capital-ish |
| Pinnacle Consulting | implementation services | per statement of work |

## Customers

| Customer | Contract | Notes |
|---|---|---|
| Northwind Trading | $50,400 annual, monthly invoicing | pays by ACH, reliably |
| Orion Health | $180,000 annual, quarterly invoicing | slow payer, takes credit memos |
| Vesta Logistics | $96,000 annual, monthly invoicing | often short-pays and explains later |
| Calder Group | $240,000 two-year, milestone billing | revenue recognition depends on milestones |
| Tallgrass Foods | $36,000 annual, annual invoicing upfront | deferred revenue |

## Known quirks a judge should know about

These exist because real ledgers have them, and because a system that only handles
clean cases is not worth deploying.

1. **Vesta Logistics short-pays**, then sends a remittance advice explaining which
   credit memo they applied. A payment that does not match an invoice is not
   automatically an exception.
2. **Cloudspan bills against blanket purchase orders** that carry no dollar amount.
   The purchase order number is real; the amount is not a control total.
3. **Orion Health's invoices are sometimes submitted twice**, once by their AP
   portal and once by email. The second copy is a duplicate, not a second liability.
4. **AWS and Cloudspan amounts move month to month**, legitimately. A 20% swing in
   infrastructure spend is not automatically a variance requiring explanation.
5. **Meridian Staffing invoices arrive after month end** for work done before it.
   Those need accruing, not rejecting.
