# Enterprise WeChat Sales Webhook Bot Design

## Goal

Build a Windows-first prototype webhook bot that watches a fixed CSV sales export, filters qualifying sales orders, attaches product images by barcode, and sends one Enterprise WeChat group robot message per qualifying order.

The prototype should validate the full workflow before the data source is replaced by a database/API and before product image URLs are provided by EMS or another internal system.

## Scope

In scope:

- Read one fixed CSV file that may be updated daily or periodically.
- Treat each CSV row as one sold product line.
- Group rows by a unique sales order number.
- Filter sales orders by configurable amount threshold or product style whitelist.
- Generate one `markdown_v2` Enterprise WeChat message per qualifying sales order.
- Include text details and up to 8 product image URLs in the same message.
- Serve local barcode-named product images through a small local HTTP image service for prototype testing.
- Persist pushed order state so the bot does not resend the same order unless state is cleared.

Out of scope for the first prototype:

- Direct database/API integration.
- EMS image lookup integration.
- Public cloud/object-storage deployment.
- User interface or admin dashboard.
- Full monitoring stack.

## Architecture

The prototype is split into small replaceable modules.

### CsvSalesDataSource

Reads the configured CSV file every scan cycle. It parses each row into a product sale line, then groups lines by sales order number.

Required logical fields:

- Sales order number.
- Sales date/time.
- Sales store.
- Sales order total amount.
- Product barcode.
- Product style number.
- Product unit price.

Optional logical fields:

- Quantity.

CSV header names are configurable because exports may use names such as `销售日期（时间）`, `销售日期时间`, or `销售时间`.

### SalesFilter

Evaluates each grouped sales order against configuration.

A sales order qualifies if it satisfies either condition:

- Sales order total amount is greater than or equal to the configured threshold.
- At least one product style number appears in the configured style whitelist.

The message includes the matched reason so recipients understand why the order was posted.

### PushStateStore

Stores local state on disk.

State includes:

- Pushed sales order numbers.
- Last scan time.
- Recent processing metadata useful for debugging.

Default behavior is to avoid duplicate posts. Each scan prioritizes orders whose sales time is later than the last scan time, then checks the pushed order number set before sending. The state can be manually cleared to resend historical orders for testing or recovery.

### ImageUrlProvider

Returns an image URL for each product line.

Prototype implementation:

- Looks for product image files in a configured local directory.
- Matches by barcode filename, such as `6901234567890.jpg` or `6901234567890.png`.
- Returns a URL hosted by the local image service.

Future implementations can replace this module with:

- EMS lookup by style number.
- Database/API image URL lookup.
- Cloud object storage URL generation.

The message builder depends only on the `ImageUrlProvider` interface, not on the storage details.

### LocalImageService

Runs a lightweight local HTTP service that exposes barcode-named product images under a configured base URL.

This service is for prototype validation. Enterprise WeChat clients must be able to access the URL for images to render. For testing, this may work on the same machine or company LAN. For broader use, image URLs should later come from a cloud server, object storage, EMS, or another reachable internal service.

### WeComWebhookClient

Sends messages to the configured Enterprise WeChat group robot webhook.

The first prototype uses `markdown_v2` because it can combine structured text and image URL markdown in one message. The client should retry temporary failures. If all retries fail, the sales order must not be marked as pushed.

## Data Flow

1. Scheduler wakes every configured interval, defaulting to 10 minutes.
2. `CsvSalesDataSource` reads the fixed CSV file.
3. Rows are parsed into product sale lines.
4. Lines are grouped by sales order number.
5. Orders older than or equal to the last scan time are skipped unless they have not been pushed and the implementation is running in a manual backfill/test mode.
6. `PushStateStore` removes orders that have already been pushed.
7. `SalesFilter` selects qualifying orders.
8. `ImageUrlProvider` resolves image URLs for each product line.
9. The message builder creates one `markdown_v2` message per qualifying order.
10. `WeComWebhookClient` sends the message.
11. On confirmed send success, `PushStateStore` records the order number as pushed.
12. The scan result is logged.

## Message Format

Each qualifying sales order produces one `markdown_v2` message.

The message includes:

- Sales order number.
- Sales time.
- Store.
- Sales order total amount.
- Matched reason.
- Product details with barcode, style number, unit price, and quantity when available.
- Missing image notes when an image is not found.
- Up to 8 product image URLs using Markdown image syntax.

If a sales order has more than 8 product images, the message shows the first 8 unique barcode images and states how many additional images were omitted. Duplicate barcodes are shown once in the image section, while product line details remain complete.

The maximum image count is configurable, defaulting to 8.

## Configuration

Use a YAML configuration file for the prototype.

Configuration values:

- CSV file path.
- CSV encoding.
- CSV field mapping.
- Image directory.
- Local image service host and port.
- Enterprise WeChat webhook URL.
- Scan interval.
- Sales amount threshold.
- Product style whitelist.
- Maximum image count per message.
- State file path.
- Log file path.
- Webhook retry count and timeout.

Secrets such as the webhook URL should be stored in local configuration that is not committed when this becomes a git project.

## Error Handling

The bot should continue running when individual records fail.

CSV read failure:

- Log the error.
- Do not advance last scan time.
- Try again on the next cycle.

Required field missing:

- Log the affected row.
- Skip that row.
- Continue processing other rows.

Order has missing product images:

- Send the text message anyway.
- Include missing barcode notes in the message.
- Do not fail the order.

Webhook send failure:

- Retry according to configuration.
- If retries are exhausted, log the failure.
- Do not mark the order as pushed.

Message too long:

- Reduce included image count first.
- If still too long, truncate product detail lines with an explicit omitted-count note.
- Preserve order number, total amount, store, time, and matched reason.

## Testing Plan

Prototype validation should cover three levels.

Parser and grouping tests:

- A small CSV with multiple rows sharing one sales order number groups into one order.
- Header mapping accepts configured Chinese column names.
- Missing optional quantity defaults safely.

Filter and state tests:

- Amount threshold match qualifies an order.
- Style whitelist match qualifies an order.
- Non-matching order is skipped.
- Previously pushed order is skipped.
- Clearing state allows resend.

Integration tests:

- Local image service returns barcode-named images.
- Message builder includes text and up to 8 image URLs.
- A test Enterprise WeChat group receives a `markdown_v2` message with multiple product images.
- If client rendering of multiple `markdown_v2` images is unstable, evaluate fallback to `news` or separate `image` messages while preserving the same data pipeline.

## Migration Path

The prototype intentionally isolates replaceable boundaries.

Data source migration:

- Replace `CsvSalesDataSource` with a database/API data source when IT provides access.
- Keep the grouped sales order model unchanged.

Image source migration:

- Replace local barcode image lookup with EMS/database/API image lookup.
- Keep `ImageUrlProvider` output as reachable image URLs.

Deployment migration:

- Move the scheduler and webhook client from the Windows prototype machine to a Windows server or Linux server.
- Move images from local HTTP service to a reachable internal or cloud-backed image service.

## Open Operational Notes

- The first prototype should include a manual one-shot run command for safe testing.
- The first prototype should include a dry-run mode that prints or logs messages without sending to Enterprise WeChat.
- The exact CSV field mapping should be finalized with a real sample export before implementation testing.
