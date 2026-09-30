"""Safe, historical descriptions for the activity log (no credential fields)."""

OBJECT_NAMES = {
    "customers.customer": "Customer", "vehicles.vehicle": "Vehicle",
    "insurance.insurancerecord": "Insurance record", "insurance.insurancecompany": "Insurance company",
    "insurance.insurancedocument": "Insurance document", "payments.payment": "Payment",
    "settings_app.businesssettings": "Business settings", "whatsapp_integration.whatsappconfig": "WhatsApp settings",
    "whatsapp_integration.whatsappmessagelog": "WhatsApp message",
    "bulk_upload.uploadtemplate": "Upload template", "bulk_upload.uploadcolumn": "Upload column",
    "bulk_upload.uploadreceipt": "Bulk import", "auth.user": "User account",
}
IDENTITY_FIELDS = {
    "name", "phone", "alternative_mobile_number", "email", "policy_number", "vehicle_number",
    "document_name", "business_name", "column_name", "username", "amount", "payment_method",
    "customer_id", "vehicle_id", "insurance_record_id", "record_id", "template_id", "insurance_company_id",
}


def describe(object_type, object_id, state, resolve, action, changes):
    """Resolve only allowlisted identity data, retaining it when records later change."""
    customer, record, vehicle = {}, {}, {}
    if object_type == "customers.customer":
        customer = state
    elif object_type == "vehicles.vehicle":
        vehicle = state
    elif object_type == "insurance.insurancerecord":
        record = state
    else:
        record_id = state.get("insurance_record_id") or state.get("record_id")
        if record_id:
            record = resolve("insurance.insurancerecord", record_id)
    if not vehicle and record.get("vehicle_id"):
        vehicle = resolve("vehicles.vehicle", record["vehicle_id"])
    customer_id = state.get("customer_id") or record.get("customer_id") or vehicle.get("customer_id")
    if not customer and customer_id:
        customer = resolve("customers.customer", customer_id)
    customer_name = str(customer.get("name") or "")
    customer_phone = str(customer.get("phone") or "")
    policy_number = str(record.get("policy_number") or "")
    vehicle_number = str(vehicle.get("vehicle_number") or "")
    object_name = OBJECT_NAMES.get(object_type, object_type.rsplit(".", 1)[-1].replace("_", " ").title())
    own_name = next((str(state[key]) for key in
                     ("name", "policy_number", "vehicle_number", "document_name", "business_name", "column_name", "username")
                     if state.get(key)), "")
    if object_type == "customers.customer":
        own_name = customer_name or customer_phone
    if state.get("template_id"):
        template = resolve("bulk_upload.uploadtemplate", state["template_id"])
    else:
        template = {}
    target = f"{object_name}: {own_name}" if own_name else f"{object_name} #{object_id}"
    if object_type == "payments.payment":
        target = f"Payment #{object_id} of Rs {state.get('amount', '')} ({state.get('payment_method') or 'payment'})"
    if object_type == "bulk_upload.uploadreceipt" and template.get("name"):
        target += f" ({template['name']})"
    verbs = {"create": "Added", "update": "Updated", "delete": "Deleted", "restore": "Restored"}
    if action == "create" and object_type == "payments.payment":
        summary = f"Collected payment of Rs {state.get('amount', '')} ({state.get('payment_method') or 'payment'})"
    elif action in ("login", "logout", "password_change"):
        summary = {"login": "Logged in", "logout": "Logged out", "password_change": "Changed password"}[action]
    else:
        summary = f"{verbs.get(action, action.title())} {target}"
    context = []
    if customer_name and own_name != customer_name:
        context.append(customer_name)
    if customer_phone and own_name != customer_phone:
        context.append(customer_phone)
    if policy_number and own_name != policy_number:
        context.append(f"Policy {policy_number}")
    if vehicle_number and own_name != vehicle_number:
        context.append(vehicle_number)
    if context:
        summary += " - " + " | ".join(context)
    action_keywords = {
        "create": "add added create created new", "update": "edit edited update updated change changed",
        "delete": "delete deleted remove removed archive archived", "restore": "restore restored recover recovered",
        "login": "login logged in", "logout": "logout logged out", "password_change": "password changed",
    }
    keywords = [summary, target, customer_name, customer_phone, policy_number, vehicle_number, action_keywords.get(action, action)]
    if record.get("insurance_company_id"):
        company = resolve("insurance.insurancecompany", record["insurance_company_id"])
        keywords.append(str(company.get("name") or ""))
    for data in (state, customer, record, vehicle, template):
        keywords.extend(str(value) for key, value in data.items() if key in IDENTITY_FIELDS and value is not None)
    # Include old identifiers/names so a rename can be found using either name.
    for key, values in changes.items():
        if key in IDENTITY_FIELDS:
            keywords.extend(str(value) for value in values.values() if value is not None)
    return dict(summary=summary[:1000], object_label=target[:512], customer_name=customer_name[:255],
                customer_phone=customer_phone[:30], policy_number=policy_number[:100],
                vehicle_number=vehicle_number[:50], search_text="\n".join(dict.fromkeys(keywords)))


def device_description(user_agent):
    if not user_agent:
        return "Unknown device"
    browsers = (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser/", "Samsung Internet"),
                ("CriOS/", "Chrome"), ("Chrome/", "Chrome"), ("FxiOS/", "Firefox"), ("Firefox/", "Firefox"),
                ("Safari/", "Safari"))
    browser = next((name for marker, name in browsers if marker in user_agent), "Other browser / API client")
    systems = (("Android", "Android"), ("iPhone", "iPhone (iOS)"), ("iPad", "iPad (iOS)"),
               ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux"))
    system = next((name for marker, name in systems if marker in user_agent), "Unknown operating system")
    return f"{browser} on {system}"
