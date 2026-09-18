# Evaluation results

Model `claude-haiku-4-5`, mode `full_context`, 26 questions x 3 pass(es) = 78 requests. Generated 2026-09-18 11:30.

| Metric | Value |
|---|---|
| Correct (first pass, graded against `eval/expected.json`) | 25/26 |
| Correct (all passes) | 76/78 |
| Answers returned without a source | 0 |
| Server latency p50 / p95 / max (ms) | 2055 / 4571 / 6302 |
| Client round-trip p50 / p95 / max (ms) | 2057 / 4573 / 6306 |
| Cost per query, mean / max (USD) | $0.00178 / $0.00298 |
| Mean tokens per query | uncached in 25.4, cache write 0, cache read 10531.0, out 139.4 |

## Answers (first pass)

### 1. How many days of annual leave do employees get?
**PASS** · status `answered` · 2034 ms · $0.00151

_What this question tests: 2024 handbook says 14 days; 2025 is current_

Confirmed employees are entitled to 20 days of paid annual leave per calendar year under the current 2025 handbook, up from 14 days in the 2024 handbook.

- `employee_handbook_2025.pdf`, page 1: "Confirmed employees are entitled to 20 days of paid annual leave per calendar year, accruing monthly. Leave requests must be submitted through the HR portal at least seven working days in"

### 2. What is the probation period for new employees?
**PASS** · status `answered` · 2925 ms · $0.00155

_What this question tests: 2024 handbook says 3 months_

The probation period for new employees is 6 months from their start date. During probation, either party may terminate employment with one week of written notice, and probation may be extended once by a maximum of one month if the review is inconclusive.

- `employee_handbook_2025.pdf`, page 1: "All new employees serve a probation period of 6 months from their start date. During probation either"

### 3. How many days per week can employees work remotely?
**PASS** · status `answered` · 1583 ms · $0.00145

_What this question tests: 2024 handbook says 1 day_

Eligible office-based employees may work remotely up to 2 days per week. Warehouse, depot and fleet roles are not eligible for remote working.

- `employee_handbook_2025.pdf`, page 1: "Eligible office-based employees may work remotely up to 2 days per week. Remote days must be"

### 4. What PPE is required in the warehouse?
**PASS** · status `answered` · 2001 ms · $0.00210

The mandatory PPE for all personnel entering the warehouse floor includes a high visibility vest (worn fastened), steel toe-capped safety boots, a hard hat in racking aisles and areas with overhead work, cut resistant gloves when handling strapped or banded pallets, and safety glasses when operating strapping or shrink wrapping equipment. PPE is issued by the depot supervisor and replaced on request at no cost to employees.

- `warehouse_safety_sop.pdf`, page 1: "The following PPE is mandatory for all personnel entering the warehouse floor, including visitors, auditors and contractors: • High visibility vest, worn fastened at all times. • Steel toe-capped safety boots. • Hard hat in all racking aisles and any area where overhead work is in progress. • Cut resistant gloves when handling strapped or banded pallets. • Safety glasses when operating strapping or shrink wrapping equipment"

### 5. What are the steps to report a safety incident?
**PASS** · status `answered` · 2917 ms · $0.00254

_What this question tests: step 6 is on page 2, split from steps 1-5_

To report a safety incident: (1) Make the area safe and summon first aid if anyone is injured; (2) Notify the shift supervisor verbally immediately; (3) Complete incident form IR-01 within 24 hours; (4) The supervisor submits the form to the Safety Officer, who logs it in the incident register; (5) The Safety Officer completes a root cause review within five working days for incidents involving injury, vehicle contact or product loss; (6) Corrective actions are assigned with an owner and due date, and reviewed at the monthly operations meeting. All incidents, including near misses with no injury or damage, must be reported.

- `warehouse_safety_sop.pdf`, page 1: "Step 1. Make the area safe and, where anyone is injured, summon first aid immediately. • Step 2. Notify the shift supervisor verbally without delay. • Step 3. Complete incident form IR-01 within 24 hours of the event. • Step 4. The supervisor submits the form to the Safety Officer, who logs it in the incident register. • Step 5. The Safety Officer completes a root cause review within five working days for any incident involving injury, vehicle contact or product loss. • Step 6. Corrective actions are assigned with an owner and a due date, and reviewed at the monthly operations meeting"

### 6. Who is allowed to operate a forklift?
**PASS** · status `answered` · 1329 ms · $0.00150

Only employees holding a current Meridian forklift certification may operate a forklift. Certification requires completion of the internal two day course, a practical assessment, and revalidation every twenty four months.

- `warehouse_safety_sop.pdf`, page 1: "Only employees holding a current Meridian forklift certification may operate a forklift. Certification"

### 7. What KYC documents are needed to onboard a new client?
**PASS** · status `answered` · 6302 ms · $0.00233

To onboard a new client, the following KYC documents must be collected and verified: certificate of incorporation or business registration certificate; National Tax Number (NTN) certificate; Sales Tax Registration Number (if applicable); CNIC copies of all directors or proprietors; board resolution or letter of authority naming the authorised signatory; bank account maintenance certificate issued within the previous three months; and two trade references from existing logistics or supplier relationships. No exceptions are granted at branch level; waivers require written approval from the Commercial Director.

- `client_onboarding_process.pdf`, page 1: "The following documents must be collected and verified before any contract is issued. No exceptions are granted at branch level; waivers require written approval from the Commercial Director. • Certificate of incorporation or business registration certificate. • National Tax Number (NTN) certificate. • Sales Tax Registration Number where the client is sales tax registered. • CNIC copies of all directors or proprietors. • Board resolution or letter of authority naming the authorised signatory. • Bank account maintenance certificate issued within the previous three months. • Two trade references from existing logistics or supplier relationships"

### 8. What is the SLA sign-off process?
**PASS** · status `answered` · 4571 ms · $0.00227

The SLA sign-off process requires four sequential approvals: (1) operations manager reviews to confirm committed transit times are achievable; (2) finance reviews to confirm rates and payment terms; (3) Commercial Director countersigns; (4) client's authorised signatory executes. The SLA is not valid until all four steps are complete and the executed copy is filed in the client folder.

- `client_onboarding_process.pdf`, page 1: "The service level agreement is drafted by the commercial lead from the standard template and must specify: committed transit times per lane, pickup cut-off times, proof of delivery turnaround, claims handling process, and the agreed rate card with its validity period. Sign-off requires, in order: review by the operations manager to confirm the committed transit times are achievable on the stated lanes; review by finance to confirm rates and payment terms; countersignature by the Commercial Director; and finally execution by the client's authorised signatory. An SLA is not valid until all four steps are complete and the executed copy is filed in the client folder"

### 9. What is the password policy?
**PASS** · status `answered` · 4162 ms · $0.00222

Meridian Logistics password policy requires passwords to be at least 12 characters with uppercase, lowercase, numerals and symbols. Passwords must be changed every 90 days and the previous five passwords cannot be reused. Multi-factor authentication is mandatory for email, the transport management system and finance portal. Passwords must never be shared, written down or stored in plain text. Accounts lock after five failed login attempts and are released by IT helpdesk only after identity verification.

- `it_security_policy.pdf`, page 1: "Passwords must be a minimum of twelve characters and include upper case, lower case, a numeral and a symbol. • Passwords must be changed every 90 days and the previous five passwords may not be reused. • Multi-factor authentication is mandatory for email, the transport management system and the finance portal. • Passwords must never be shared, written down, or stored in plain text in any document or spreadsheet. • Accounts are locked after five consecutive failed attempts and released only by the IT helpdesk after identity verification"

### 10. Is VPN required for remote access?
**PASS** · status `answered` · 2593 ms · $0.00141

Yes, VPN is mandatory for all remote access to internal systems. No internal system may be reached from outside the corporate network without an established VPN session.

- `it_security_policy.pdf`, page 1: "VPN is mandatory for all remote access to internal systems. No internal system may be reached from"

### 11. What was revenue in Q3 2025?
**PASS** · status `answered` · 1342 ms · $0.00138

Revenue in Q3 2025 was PKR 412.6 million.

- `quarterly_review_q3_2025.pdf`, page 1: "Revenue for the third quarter of 2025 was PKR 412.6 million, an increase of 14 percent on the same"

### 12. How many people does the company employ?
**PASS** · status `answered` · 2966 ms · $0.00298

As of the end of Q3 2025, Meridian Logistics employed 487 people.

- `quarterly_review_q3_2025.pdf`, page 1: "The company employed 487 people at the close of the quarter, up from 465 at the end of Q2. Growth"

### 13. Which new clients were won in Q3 2025?
**PASS** · status `answered` · 3704 ms · $0.00235

Two significant clients were won in Q3 2025: Tariq Textiles (Private) Limited, a three-year warehousing and distribution agreement at the Lahore depot with estimated annual revenue of PKR 46 million; and Crescent Pharma Distribution, a two-year line-haul agreement for the Karachi to Lahore and Karachi to Islamabad lanes with estimated annual revenue of PKR 31 million.

- `quarterly_review_q3_2025.pdf`, page 1: "Two significant clients were won during the quarter: • Tariq Textiles (Private) Limited. A three year warehousing and distribution agreement covering 4,200 square feet of racked storage at the Lahore depot and outbound distribution to retail locations in Punjab. Estimated annual revenue PKR 46 million. • Crescent Pharma Distribution. A two year line-haul agreement covering the Karachi to Lahore and Karachi to Islamabad lanes, with committed temperature-controlled capacity. Estimated annual revenue PKR 31 million. First shipment moved 22 August 2025"

### 14. What is the policy on personal devices?
**PASS** · status `answered` · 3633 ms · $0.00231

Personal devices may be used to access company email and calendar only if enrolled in mobile device management. Enrolment requires a device passcode, full device encryption, and IT remote-wipe capability. Client data, shipment records, and financial data may not be stored on personal devices, and company documents cannot be transferred to personal cloud storage or personal email accounts. Lost or stolen enrolled devices must be reported to IT within two hours, and company data is remotely wiped when employees leave.

- `it_security_policy.pdf`, page 1: "Personal devices may be used to access company email and calendar only, and only where the device is enrolled in mobile device management. Enrolment requires a device passcode, full device encryption and the ability for IT to remotely wipe company data. • Client data, shipment records and financial data may not be stored on personal devices. • Company documents may not be transferred to personal cloud storage or personal email accounts. • Lost or stolen personal devices with enrolled company access must be reported to IT within two hours. • On leaving the company, enrolled personal devices are remotely wiped of the company profile as part of exit clearance"

### 15. What is the rate for a 1,200 kg shipment from Lahore to Karachi?
**PASS** · status `answered` · 2813 ms · $0.00199

_What this question tests: 1,200 kg falls in the 500 kg - 2 T band (PKR 24,500); with the 6.5% fuel surcharge PKR 26,092.50, excl. sales tax_

For a 1,200 kg shipment from Lahore to Karachi, the base rate is PKR 24,500 (in the 500 kg – 2 T weight band). With the 6.5% fuel surcharge applied, the total is PKR 24,500 × 1.065 = PKR 26,092.50, exclusive of sales tax.

- `pricing_sheet_2025.pdf`, page 1: "| Lahore | Karachi | 1,240 | 8,600 | 24,500 | 78,000 | 6.5% |"
- `pricing_sheet_2025.pdf`, page 1: "Weight bands are inclusive of the lower bound and exclusive of the upper bound. Consignments above"

### 16. Which route is most expensive per kg in the 2T-10T band?
**FAIL** · status `answered` · 3124 ms · $0.00200 · problems: ["missing ['Karachi']", "missing ['88500']"]

_What this question tests: band rates are flat per consignment, so per kg at equal weight the highest band rate wins: Karachi-Islamabad PKR 88,500 (94,695 with 7% fuel; Islamabad-Gilgit 84,000 / 93,240 with 11%)_

The Islamabad to Gilgit route is most expensive per kg in the 2T-10T band at 84,000 PKR. Per kg, this is 84,000 ÷ 2,000 = 42 PKR/kg (using the lower bound of the band, assuming minimum 2 tonnes). This rate is exclusive of sales tax.

- `pricing_sheet_2025.pdf`, page 1: "Row - Origin: Islamabad; Destination: Gilgit; Distance (km): 600; 0 - 500 kg: 9,100; 500 kg - 2 T: 26,400; 2 T - 10 T: 84,000; Fuel surcharge: 11.0%."

### 17. Is there a fuel surcharge on the Karachi-Quetta route?
**PASS** · status `answered` · 2118 ms · $0.00170

Yes, there is a fuel surcharge of 9.5% on the Karachi-Quetta route.

- `pricing_sheet_2025.pdf`, page 1: "Row - Origin: Karachi; Destination: Quetta; Distance (km): 690; 0 - 500 kg: 7,200; 500 kg - 2 T: 21,800; 2 T - 10 T: 71,500; Fuel surcharge: 9.5%."

### 18. What are the payment terms in the vendor agreement?
**PASS** · status `answered` · 2119 ms · $0.00152

_What this question tests: scanned image, needs OCR; client payment terms (30 days, onboarding doc) are a distractor_

Vendor payment terms are Net 45 days from the date of a correctly rendered invoice. Invoices disputed in good faith are paid within 45 days of resolution of the dispute, and no early settlement discount applies.

- `vendor_agreement_scanned.pdf`, page 1: "The Vendor shall invoice the Company monthly in arrears. Vendor payment terms are Net 45 days from the date of a correctly rendered invoice."

### 19. What is the deadline for filing a damaged cargo claim?
**PASS** · status `answered` · 1696 ms · $0.00145

_What this question tests: single paragraph on page 29 of a 67-page manual of boilerplate_

Damaged cargo claims must be filed within 7 working days of delivery. Claims received after this deadline are rejected without assessment, regardless of the merits of the underlying damage.

- `operations_manual_full.pdf`, page 29: "Claims must be initiated by the consignee or the client's authorised representative. Damaged cargo claims must be filed within 7 working days of delivery. Claims received after this window are"

### 20. Has the leave policy changed recently?
**PASS** · status `answered` · 3465 ms · $0.00239

_What this question tests: must compare the two handbook versions_

Yes. Annual leave has increased from 14 days to 20 days per calendar year, and the carry-forward limit has increased from 5 days to 7 days. These changes are reflected in the current 2025 handbook (up from the 2024 version). Sick leave remains unchanged at 10 days per year.

- `employee_handbook_2024.pdf`, page 1 (superseded by employee_handbook_2025.pdf): "Confirmed employees are entitled to 14 days of paid annual leave per calendar year, accruing monthly. Leave requests must be submitted through the HR portal at least seven working days in advance and require line manager approval. Up to 5 days of unused leave may be carried into the following year; any balance above that is forfeited on 31 December."
- `employee_handbook_2025.pdf`, page 1: "Confirmed employees are entitled to 20 days of paid annual leave per calendar year, accruing monthly. Leave requests must be submitted through the HR portal at least seven working days in advance and require line manager approval. Up to 7 days of unused leave may be carried into the following year; any balance above that is forfeited on 31 December."

### 21. What is the current probation period for new hires?
**PASS** · status `answered` · 1621 ms · $0.00145

The current probation period for new hires is 6 months from their start date, up from 3 months in the 2024 handbook.

- `employee_handbook_2025.pdf`, page 1: "All new employees serve a probation period of 6 months from their start date. During probation either"

### 22. What is the salary range for a warehouse supervisor?
**PASS** · status `not_found` · 1187 ms · $0.00122

_What this question tests: no salary information anywhere in the corpus_

The documents provided do not contain information about salary ranges for any position, including warehouse supervisors.


### 23. What does the company health insurance cover?
**PASS** · status `not_found` · 1493 ms · $0.00136

_What this question tests: only vendor public liability insurance exists; no employee health insurance_

The documents provided do not cover company health insurance. The employee handbook sets out entitlements including probation, annual leave, sick leave, remote working, notice periods and code of conduct, but does not describe health insurance coverage.


### 24. What is the maternity leave policy?
**PASS** · status `not_found` · 1605 ms · $0.00134

_What this question tests: handbook covers annual and sick leave only_

The documents provided do not cover maternity leave policy. The employee handbooks detail annual leave, sick leave, and remote working arrangements, but do not mention maternity leave or any other leave types beyond those.


### 25. Who is the CEO of Meridian Logistics?
**PASS** · status `not_found` · 2604 ms · $0.00122

_What this question tests: no CEO named; only roles like Commercial Director_

The documents provided do not contain information about who the CEO of Meridian Logistics is.


### 26. What is the refund policy for delayed international shipments?
**PASS** · status `not_found` · 1775 ms · $0.00134

_What this question tests: no refund policy and no international service; claims section covers damage only_

The documents provided do not cover refund policies for delayed international shipments. The pricing sheet and operational procedures focus on domestic Pakistani freight services, and there is no section addressing refunds, service credits, or compensation for delays.

