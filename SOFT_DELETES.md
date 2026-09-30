Application models use `deleted_at` and `deletion_batch` for archival deletion.
Instance, queryset, API and Django admin deletion retain database rows. Owned
CASCADE children are archived in the same transaction; SET_NULL relationships
remain intact, preserving audit references and renewal lineage. Uploaded files
are retained. Authentication tokens still expire/revoke through physical deletion.
Deleting a Django user is protected when session activity exists.

Apply the schema before running the updated application:

```powershell
python manage.py migrate
```

Normal `objects` queries and reverse collections exclude archived rows. Internal
recovery/audit code can use `Model.all_objects`. SQL joins bypass related managers,
so related financial annotations must explicitly filter `deleted_at__isnull=True`.
Archived unique identifiers remain reserved; restore the original record rather
than creating a duplicate vehicle, policy number, company or template.

Recover an accidental deletion (using the original record ID):

In Django admin, open the model list and choose **Deletion status → Deleted**
in the right-hand filter panel. **All** displays both active and deleted rows;
the default is **Active**. The list shows a Deleted indicator and deletion date.
Deleted record detail pages are read-only. Superusers can select deleted rows,
choose **Restore selected deleted records**, and click **Go**. This restores
each selected deletion batch, including its related records. Recovery conflicts
are displayed as admin messages without partially restoring a batch.

Alternatively, use the management command:

```powershell
python manage.py restore_record customers.Customer 123
```

Recovery restores the entire deletion batch, including its archived children,
without restoring records deleted earlier. Restore archived parents first when
they belong to a separate batch. Conflicting active policies or payment balances
cause an atomic rollback. The same operation is available in application code:
`Customer.all_objects.get(pk=123).restore()`.

There is no application hard-delete or purge endpoint. Previously physically
deleted data requires a database backup; this change cannot reconstruct it.
