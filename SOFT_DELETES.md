Application models use `deleted_at` and `deletion_batch` for archival deletion.
Instance, queryset, API and initial Django admin deletion retain database rows. Owned
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
Deleted record detail pages are read-only, with deletion still available to users
with the required delete permissions. Superusers can select deleted rows,
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

To permanently remove archived records in Django admin, select them under the
Deleted filter and use **Delete selected**, then confirm. The confirmation shows
the physical deletion cascade and states that archived records cannot be restored.
The detail-page Delete button has the same behavior. Active records are still
archived; a mixed selection under All purges only records already archived when
the action starts. Related delete permissions and protected relationships are
enforced. A purge is blocked if it would also delete active dependent records.
SET_NULL references are cleared using Django's normal physical deletion behavior.
Uploaded files are retained.

There is no application API purge endpoint. Permanently deleted data requires a
database backup to recover.
