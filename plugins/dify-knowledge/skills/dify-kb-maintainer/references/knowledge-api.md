# Dify Knowledge API

The plugin has a built-in LAN default:

```text
http://192.168.97.251:8080/v1
```

Override it when needed:

```sh
export DIFY_BASE_URL=http://192.168.97.251:8080/v1
export DIFY_API_KEY=dataset-...
```

Or store local settings next to the helper script:

```sh
python3 scripts/dify_kb.py configure --api-key dataset-... --base-url http://192.168.97.251:8080/v1
```

All requests use:

```text
Authorization: Bearer <api_key>
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

For the primary project-memory knowledge base, prefer hybrid retrieval with weighted-score reranking and a project metadata filter:

```json
{
  "search_method": "hybrid_search",
  "reranking_enable": true,
  "reranking_model": {
    "reranking_provider_name": "",
    "reranking_model_name": ""
  },
  "reranking_mode": "weighted_score",
  "weights": {
    "vector_setting": {
      "vector_weight": 0.5,
      "embedding_provider_name": "langgenius/openai/openai",
      "embedding_model_name": "text-embedding-3-large"
    },
    "keyword_setting": {
      "keyword_weight": 0.5
    }
  },
  "top_k": 12,
  "score_threshold_enabled": false,
  "metadata_filtering_conditions": {
    "logical_operator": "and",
    "conditions": [
      {
        "name": "project_key",
        "comparison_operator": "is",
        "value": "<project_key>"
      }
    ]
  }
}
```

The helper also applies project-card topic expansion and client-side card ordering when `--project-key` is used. This is intentionally scoped to the primary project-memory knowledge base shape: one healthy project document contains nine parent cards from project overview through endpoint index.

Use `keyword_search` with `economy` datasets for simple no-embedding smoke tests.
