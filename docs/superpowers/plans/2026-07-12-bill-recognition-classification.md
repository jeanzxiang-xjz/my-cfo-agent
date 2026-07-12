# Bill Recognition and Classification Implementation Plan

## Global Constraints

- macOS Vision remains the only OCR engine; raw screenshots and OCR text stay local.
- DeepSeek may change only category metadata, never amount, time, merchant, payment method, or identifiers.
- Existing `parse_bill_text()` and `store_bill_capture()` call signatures remain compatible.
- Manual overrides take precedence over merchant memory, local rules, DeepSeek, and pending fallback.
- DeepSeek receives only merchant, product, platform, and payment app fields.
- Classification runs in the background and must not extend the `/api/sync-mail` response path.
- Full-ledger changes require an integrity-checked timestamped backup and dry-run report first.

### Task 1: Deterministic parser and local taxonomy

Create regression fixtures and `unittest` coverage for the new WeChat transaction-detail layout, legacy WeChat, and Alipay. Fix merchant extraction around the amount, reject generic page labels with OCR prefixes, add `经营单号` and `交易服务` field boundaries, normalize OCR-split matching text, introduce the fixed taxonomy plus local classification result, and separate parse confidence from category confidence.

Acceptance: the two known bad WeChat samples resolve to `易友佳便利店` and `A卓越中寰体彩`; transaction and merchant-order IDs contain only their identifiers; lottery, small-shop groceries, OCR-split Meituan, and personal QR transfer classifications pass.

### Task 2: Classification persistence and precedence

Extend SQLite schema with classification metadata, `merchant_category_memory`, and `transaction_overrides`. Apply precedence `override > memory > local rule > pending`, reject unstable merchant keys, and preserve current call signatures. Add tests for schema migration, memory conflicts, generic merchants, overrides, and idempotent capture storage.

### Task 3: Privacy-limited DeepSeek background enrichment

Add strict fixed-enum JSON classification through the configured DeepSeek model, batch at most 10 pending transactions, reject invalid/unknown results, and leave failures pending. Trigger a single locked daemon worker after mail sync and at server startup without blocking sync. Test request privacy, valid/invalid responses, timeout behavior, and worker locking.

### Task 4: Safe full-ledger audit and reprocessing

Replace the limited category backfill with a dry-run-first audit command that backs up SQLite, checks integrity, preserves manual differences, reparses by `raw_capture_hash`, reconciles corrected transaction UIDs without duplicates, applies high-confidence local changes, and queues uncertain rows. Add temporary-database tests for dry-run immutability, backup creation, overrides, UID repair, and transaction-count stability.

### Task 5: Web payload, labels, documentation, and live validation

Expose classification status/source/confidence/reason in `/data.json`, add the five category labels to Python and frontend maps, display pending items as `识别中`, and poll briefly after sync while pending classification exists. Update README architecture and privacy notes. Build the frontend, run all tests, then execute dry-run and apply against the real ledger only after a timestamped backup. Verify zero generic `交易详情` merchants, zero malformed identifiers, no loss of the `apple礼品卡` override, and at most five unresolved rows after enrichment.
