# Bulk Excel upload

Open **Bulk Upload** in the application sidebar. Select a customer or insurance
template, download its Excel file, fill the first worksheet, validate it, and
review the preview before importing. Validation does not save any records.

For files containing only `S. DATE`, `E. DATE`, `CUT.NAME`, `VEHICAL NO`,
`CO NAME`, `NET PR.`, and `TOTAL.`, select **Compact Insurance Records**.
This template also accepts the descriptive column names, such as Start Date,
Customer Name, Vehicle Number, Net Premium, and Total Premium. Blank spacer
columns are allowed. `02.10.2025` means 2 October 2025.

Mobile and policy numbers are not required for this template. New customers
have a blank phone; existing customers are matched by vehicle owner first,
then by a unique customer name (case insensitive). Ambiguous names or a
different vehicle owner require review. Existing phone numbers are preserved.
Bulk customer-name matching ignores case, whitespace, and punctuation (including
periods in initials). Matching an existing vehicle reuses its customer ID rather
than creating another customer for a differently formatted name. Genuine owner
conflicts report both the existing and uploaded customer names.
Missing policy numbers receive a stable `BULK-` reference based on vehicle and
coverage dates, so repeated uploads are detected as duplicates. Net premium
uses the application's existing definition: total premium minus discount.
The importer calculates discount as `TOTAL. - NET PR.` and rejects negative
net premiums or net premiums greater than the total. Existing company and
policy validation rules still apply. The standard templates remain unchanged.

`NEW` and `NEW(...)` vehicle placeholders receive a stable temporary identifier
for each customer, so different customers using the same placeholder do not share
a vehicle or policy reference. Preview warnings show the assigned identifier.
Use the actual registration when available. Repeated placeholders for the same
customer still use the same vehicle; genuine registration ownership conflicts
remain errors and identify the earlier Excel row when applicable.

## Re-import after deleting records

Deletion archives records and reserves their identifiers. Bulk insurance imports
now recover a matching archived policy instead of attempting to insert another
row with the same policy number. If the spreadsheet has no policy number,
matching uses vehicle, insurer, and coverage dates, including older `AUTO-`
references. Recovery reuses the original policy ID/reference and applies the
spreadsheet values through the existing serializer. Matching customer and vehicle
links are recovered. If a deleted vehicle has a different archived owner and no
live policies, the uploaded customer is resolved or created and becomes the owner
of the recovered vehicle and matching policy. The preview and import show an Excel
row warning naming the old and new owners. The old customer and unrelated archived
policies remain archived. Live vehicles and vehicles with live policies still
reject ownership conflicts. An archived vehicle can also be reused for new coverage.
Customer uploads restore matching deleted customers instead of skipping them or
creating duplicates; their archived vehicles and policies remain archived.

Only the matching policy and required parent rows are recovered. Other rows in
the deletion batch, payments, and documents remain archived. Preview rolls back
all recovery changes; any row error rolls back the whole import. Live duplicate
policies, conflicting owners, and active/scheduled policy conflicts remain errors.
Preview/import results show restored policies separately from newly created rows.
The recovery migration also adds an optional `NET PR.` mapping to existing
insurance templates that do not already map net premium, including custom ones.

## Configure columns in Django Admin

Visit `/admin/` → **Bulk upload** → **Bulk upload templates**. The migrations
create `Standard Customers` and `Standard Insurance Records`. You can also create
a separate template for each client's format.

For each template, edit the inline columns:

- **Column name:** Excel header and downloaded sample header.
- **Field name:** existing customer/insurance field receiving that value.
- **Aliases:** alternative headers, one per line.
- **Required:** require a value in every nonempty row.
- **Default value:** use when the cell or column is missing.
- **Position:** order in the sample file.
- **Active:** include or exclude the column.

Optional columns can be added, deleted, or disabled. Required system mappings
must remain active and be required or have a default. Duplicate mappings or
overlapping names/aliases are rejected. Header matching ignores case, whitespace,
hyphens, and underscores. A template's target cannot change after creation;
create another template to switch from customers to insurance records.

Columns map to supported fields that already exist in the project. Adding a
brand-new database field requires a code change and migration. The expected data
type follows the mapped field automatically. Defaults for dates and numbers are
checked when the template is saved. There are no frontend configuration writes.

## Import rules

- `.xlsx` only, at most 10 MB and 2,000 data rows (including blank rows).
- Row 1 contains headers on the first worksheet; other sheets are ignored.
- Dates accept native Excel dates, `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, or `DD.MM.YYYY`.
- Phone, vehicle, and policy numbers should be stored as text. Excel cannot
  recover leading zeros or digits it already rounded in a numeric cell.
- Formulas and Excel errors in mapped cells are rejected. Unmapped headers
  are ignored with a visible warning.
- Blank rows are ignored. Row errors use the original Excel row numbers and
  can be downloaded as a CSV report.
- Existing customers with the same normalized phone and supplied name
  (case insensitive) are skipped without changing their details. If no name is
  provided, an existing customer with that phone is skipped.
- Insurance rows use the existing creation serializer, including its customer
  resolution and optional customer-detail updates. Companies must already exist
  and be active; enter their exact names (case insensitive).
- Duplicate policies, multiple active policies for a vehicle, invalid dates,
  premiums/discounts, and conflicting vehicle ownership are rejected. Bulk
  uploads do not renew existing policies or create initial payments/documents;
  use the existing screens for those operations.
- All rows must pass. Any error rolls back the entire upload, including related
  customer/vehicle changes. Imports revalidate against current database state.
- A successful preview is required before import. It expires in 30 minutes and
  is bound to the user, file, and template configuration. Changing columns or
  file contents requires another validation. A successful preview can only be
  imported once. Receipts are visible in Django Admin.

## Installation / deployment

From the backend directory:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe manage.py migrate
```

Deploy/restart the backend and rebuild/restart the frontend using the project's
existing deployment procedure. The new routes are `/bulk-upload` on the frontend
and `/api/bulk-upload/` on the backend. Template listing/download and preview/import
require the same authentication as the existing data-entry APIs.

## Verification

```powershell
venv\Scripts\python.exe manage.py test bulk_upload customers insurance vehicles payments --noinput
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

From the frontend directory, run `npx.cmd tsc --noEmit`,
`npx.cmd eslint app/bulk-upload/page.tsx lib/bulk-upload-api.ts`, and `npm.cmd run build`.
