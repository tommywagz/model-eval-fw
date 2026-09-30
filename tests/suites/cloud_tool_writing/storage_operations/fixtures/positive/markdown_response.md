Here's a storage tool that routes each record to the right backend. It handles setup idempotently
and keeps binary payloads as raw bytes end to end.

```python
import base64
import json


class _Router:
    def __init__(self, clients):
        self.c = clients

    # ---- store -------------------------------------------------------------
    def store_bigquery(self, r):
        bq = self.c.bigquery
        if not bq.dataset_exists(r["dataset"]):
            bq.create_dataset(r["dataset"])
        if not bq.table_exists(r["table"]):
            try:
                bq.create_table(r["table"], r["schema"])
            except self.c.errors.Conflict:
                pass  # created concurrently / earlier in this run
        errs = bq.insert_rows(r["table"], [r["row"]])
        if errs:
            raise self.c.errors.BadRequest(json.dumps(errs))

    def store_gcs(self, r):
        gcs = self.c.gcs
        if not gcs.bucket_exists(r["bucket"]):
            gcs.create_bucket(r["bucket"])
        if "json" in r:
            payload = json.dumps(r["json"], ensure_ascii=False).encode("utf-8")
            gcs.upload_bytes(r["bucket"], r["object"], payload, "application/json")
        else:
            gcs.upload_bytes(r["bucket"], r["object"], base64.b64decode(r["content_base64"]), r["content_type"])

    def store_firestore(self, r):
        self.c.firestore.set_document(r["collection"], r["doc_id"], dict(r["data"]))

    # ---- retrieve ----------------------------------------------------------
    def get_bigquery(self, q):
        rows = self.c.bigquery.list_rows(q["table"])
        where = q.get("where") or {}
        hits = [row for row in rows if all(row.get(k) == v for k, v in where.items())]
        if q.get("order_by"):
            hits.sort(key=lambda row: row[q["order_by"]])
        return hits

    def get_gcs(self, q):
        raw = self.c.gcs.download_bytes(q["bucket"], q["object"])
        return json.loads(raw.decode("utf-8")) if q["format"] == "json" else raw

    def get_firestore(self, q):
        doc = self.c.firestore.get_document(q["collection"], q["doc_id"])
        if doc is None:
            raise self.c.errors.NotFound(f"{q['collection']}/{q['doc_id']}")
        if not q.get("field"):
            return doc
        value = doc
        for part in q["field"].split("."):
            value = value[part]
        return value


def store_record(clients, record):
    getattr(_Router(clients), f"store_{record['store']}")(record)


def retrieve_record(clients, request):
    return getattr(_Router(clients), f"get_{request['store']}")(request)
```

BigQuery reads use `list_rows` with client-side filtering, so they never depend on the SQL
dialect. Firestore field paths are resolved by walking the document map.
