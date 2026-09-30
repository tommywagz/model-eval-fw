"""Reference storage tool: idempotent setup, parameterized SQL, exact byte handling."""

import base64


def _ensure_table(bq, record):
    bq.create_dataset(record["dataset"], exists_ok=True)
    bq.create_table(record["table"], record["schema"], exists_ok=True)


def store_record(clients, record):
    store = record["store"]
    if store == "bigquery":
        _ensure_table(clients.bigquery, record)
        errors = clients.bigquery.insert_rows(record["table"], [record["row"]])
        if errors:
            raise RuntimeError(f"BigQuery insert failed for {record['record_id']}: {errors}")
    elif store == "gcs":
        clients.gcs.create_bucket(record["bucket"], exists_ok=True)
        if "json" in record:
            clients.gcs.upload_json(record["bucket"], record["object"], record["json"])
        else:
            data = base64.b64decode(record["content_base64"])
            clients.gcs.upload_bytes(record["bucket"], record["object"], data, record["content_type"])
    elif store == "firestore":
        clients.firestore.set_document(record["collection"], record["doc_id"], record["data"])
    else:
        raise ValueError(f"unknown store {store!r}")


def retrieve_record(clients, request):
    store = request["store"]
    if store == "bigquery":
        where = request.get("where", {})
        params = {f"p{i}": v for i, v in enumerate(where.values())}
        clauses = [f"{col} = @p{i}" for i, col in enumerate(where)]
        sql = f"SELECT * FROM `{request['table']}`"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if request.get("order_by"):
            sql += f" ORDER BY {request['order_by']} ASC"
        return clients.bigquery.query(sql, params=params)
    if store == "gcs":
        if request["format"] == "json":
            return clients.gcs.download_json(request["bucket"], request["object"])
        return clients.gcs.download_bytes(request["bucket"], request["object"])
    if store == "firestore":
        if request.get("field"):
            return clients.firestore.get_field(request["collection"], request["doc_id"], request["field"])
        return clients.firestore.get_document(request["collection"], request["doc_id"])
    raise ValueError(f"unknown store {store!r}")
