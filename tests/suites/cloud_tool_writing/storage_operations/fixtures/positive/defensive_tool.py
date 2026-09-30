"""Defensive storage tool: validates inputs, retries idempotent setup, uses SQL literals safely."""

import base64

_SETUP_DONE = set()


def _sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _setup_once(key, fn):
    if key in _SETUP_DONE:
        return
    fn()
    _SETUP_DONE.add(key)


def store_record(clients, record):
    if not isinstance(record, dict) or "store" not in record:
        raise ValueError("record must be a dict with a 'store' key")
    kind = record["store"]
    if kind == "bigquery":
        bq = clients.bigquery
        _setup_once(("ds", record["dataset"]), lambda: bq.create_dataset(record["dataset"], exists_ok=True))
        _setup_once(("tb", record["table"]), lambda: bq.create_table(record["table"], record["schema"], exists_ok=True))
        problems = bq.insert_rows(record["table"], [dict(record["row"])])
        if problems:
            raise RuntimeError(problems)
        return
    if kind == "gcs":
        gcs = clients.gcs
        _setup_once(("bk", record["bucket"]), lambda: gcs.create_bucket(record["bucket"], exists_ok=True))
        if record.get("content_type") == "application/json" and "json" in record:
            gcs.upload_json(record["bucket"], record["object"], record["json"])
        else:
            blob = base64.b64decode(record["content_base64"], validate=True)
            gcs.upload_bytes(record["bucket"], record["object"], blob, content_type=record["content_type"])
        meta = gcs.get_metadata(record["bucket"], record["object"])
        if meta["content_type"] != record["content_type"]:
            raise RuntimeError(f"content type drift: {meta}")
        return
    if kind == "firestore":
        clients.firestore.set_document(record["collection"], record["doc_id"], record["data"], merge=False)
        return
    raise ValueError(f"unsupported store: {kind}")


def retrieve_record(clients, request):
    kind = request["store"]
    if kind == "bigquery":
        conds = " AND ".join(f"{k} = {_sql_literal(v)}" for k, v in (request.get("where") or {}).items())
        sql = "SELECT * FROM `%s`" % request["table"]
        if conds:
            sql += " WHERE " + conds
        if request.get("order_by"):
            sql += " ORDER BY " + request["order_by"]
        return clients.bigquery.query(sql)
    if kind == "gcs":
        fetch = clients.gcs.download_json if request["format"] == "json" else clients.gcs.download_bytes
        return fetch(request["bucket"], request["object"])
    if kind == "firestore":
        try:
            if "field" in request and request["field"]:
                return clients.firestore.get_field(request["collection"], request["doc_id"], request["field"])
            return clients.firestore.get_document(request["collection"], request["doc_id"])
        except clients.errors.NotFound:
            raise
    raise ValueError(f"unsupported store: {kind}")
