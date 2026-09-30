# Bulk Excel upload

Open **Bulk Upload** in the application sidebar. Select a customer or insurance
template, download its Excel file, fill the first worksheet, validate it, and
review the preview before importing. Validation does not save any records.

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
- Dates accept native Excel dates, `YYYY-MM-DD`, `DD/MM/YYYY`, or `DD-MM-YYYY`.
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
