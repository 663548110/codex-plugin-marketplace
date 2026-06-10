# Dify Knowledge API

Set:

```sh
export DIFY_BASE_URL=http://192.168.97.251:8080/v1
export DIFY_API_KEY=dataset-...
```

Or store local settings next to the helper script:

```sh
python3 scripts/dify_kb.py configure --api-key dataset-... --base-url http://192.168.97.251:8080/v1
```

All requests need:

```text
Authorization: Bearer $DIFY_API_KEY
```

Create or get a key in Dify UI:

```text
Knowledge -> Service API -> API Key
```

## Useful Endpoints

- `GET /datasets`: list knowledge bases
- `POST /datasets`: create an empty knowledge base
- `GET /datasets/{dataset_id}/documents`: list documents
- `GET /datasets/{dataset_id}/documents/{document_id}`: get document
- `POST /datasets/{dataset_id}/document/create-by-text`: create a text document
- `POST /datasets/{dataset_id}/document/create-by-file`: upload file as document
- `GET /datasets/{dataset_id}/documents/{document_id}/indexing-status`: check indexing
- `POST /datasets/{dataset_id}/retrieve`: retrieve or hit-test chunks
- `POST /datasets/{dataset_id}/metadata`: create metadata field

## Retrieval Notes

For Dify 1.14, `retrieval_model` requires:

```json
{
  "search_method": "keyword_search",
  "reranking_enable": false,
  "reranking_model": null,
  "reranking_mode": null,
  "top_k": 3,
  "score_threshold_enabled": false
}
```

Use `keyword_search` with `economy` datasets for simple no-embedding smoke tests.
