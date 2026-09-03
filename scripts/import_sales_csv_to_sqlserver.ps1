param(
    [string]$CsvPath = "C:\Users\x\Desktop\Test\sales.csv",
    [string]$Server = "localhost",
    [string]$Database = "wecom_sales_test",
    [switch]$TruncateFirst = $true,
    [ValidateSet("Auto", "Default", "UTF8", "Unicode", "BigEndianUnicode")]
    [string]$Encoding = "Auto"
)

Add-Type -AssemblyName System.Data

function Get-ColumnValueByIndex {
    param(
        $Row,
        [int]$Index
    )

    $properties = @($Row.PSObject.Properties)
    if ($Index -lt 0 -or $Index -ge $properties.Count) {
        return $null
    }

    $value = [string]$properties[$Index].Value
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $null
    }

    return $value.Trim()
}

function Parse-SoldAt {
    param(
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "sold_at is empty"
    }

    $formats = @(
        "yyyy/M/d H:mm:ss",
        "yyyy/M/d H:mm",
        "yyyy/M/d h:mm tt",
        "yyyy-MM-dd H:mm:ss",
        "yyyy-MM-dd H:mm",
        "yyyy-MM-ddTHH:mm:ss"
    )

    foreach ($format in $formats) {
        try {
            return [datetime]::ParseExact(
                $Value,
                $format,
                [System.Globalization.CultureInfo]::InvariantCulture
            )
        }
        catch {
        }
    }

    try {
        return [datetime]::Parse($Value)
    }
    catch {
        throw "cannot parse sold_at: $Value"
    }
}

function Resolve-CsvEncoding {
    param(
        [string]$Path,
        [string]$RequestedEncoding
    )

    if ($RequestedEncoding -ne "Auto") {
        return $RequestedEncoding
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return "UTF8"
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        return "Unicode"
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        return "BigEndianUnicode"
    }

    return "Default"
}

if (-not (Test-Path $CsvPath)) {
    throw "CSV file not found: $CsvPath"
}

$resolvedEncoding = Resolve-CsvEncoding -Path $CsvPath -RequestedEncoding $Encoding
Write-Host "Using CSV encoding: $resolvedEncoding" -ForegroundColor Yellow
$rows = @(Import-Csv -Path $CsvPath -Encoding $resolvedEncoding)
if ($rows.Count -eq 0) {
    throw "CSV has no data rows: $CsvPath"
}

$firstRowProperties = @($rows[0].PSObject.Properties)
if ($firstRowProperties.Count -lt 7) {
    throw "CSV must contain at least 7 columns: order_no, sold_at, store_name, total_amount, barcode, style_no, unit_price"
}

$connectionString = "Server=$Server;Database=$Database;Integrated Security=True;TrustServerCertificate=True;"
$connection = New-Object System.Data.SqlClient.SqlConnection $connectionString
$connection.Open()
$transaction = $connection.BeginTransaction()
$importedCount = 0
$skippedEmptyRows = 0

try {
    if ($TruncateFirst) {
        $clearCmd = $connection.CreateCommand()
        $clearCmd.Transaction = $transaction
        $clearCmd.CommandText = "DELETE FROM dbo.sales_lines"
        [void]$clearCmd.ExecuteNonQuery()
    }

    foreach ($row in $rows) {
        # The first seven columns follow the project's standard sales CSV layout.
        $orderNo = Get-ColumnValueByIndex $row 0
        $soldAtRaw = Get-ColumnValueByIndex $row 1
        $storeName = Get-ColumnValueByIndex $row 2
        $totalAmountRaw = Get-ColumnValueByIndex $row 3
        $barcode = Get-ColumnValueByIndex $row 4
        $styleNo = Get-ColumnValueByIndex $row 5
        $unitPriceRaw = Get-ColumnValueByIndex $row 6

        $requiredValues = @($orderNo, $soldAtRaw, $storeName, $totalAmountRaw, $barcode, $styleNo, $unitPriceRaw)
        if (($requiredValues | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count -eq 0) {
            $skippedEmptyRows++
            continue
        }
        if (($requiredValues | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
            Write-Warning "Skipping row with missing required value"
            continue
        }

        $soldAt = Parse-SoldAt $soldAtRaw
        $totalAmount = [decimal]$totalAmountRaw
        $unitPrice = [decimal]$unitPriceRaw
        $brand = Get-ColumnValueByIndex $row 7
        $category = Get-ColumnValueByIndex $row 8
        $imageUrl = Get-ColumnValueByIndex $row 9

        $cmd = $connection.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = @"
INSERT INTO dbo.sales_lines
(
    order_no,
    sold_at,
    store_name,
    total_amount,
    barcode,
    style_no,
    unit_price,
    brand,
    category,
    image_url
)
VALUES
(
    @order_no,
    @sold_at,
    @store_name,
    @total_amount,
    @barcode,
    @style_no,
    @unit_price,
    @brand,
    @category,
    @image_url
)
"@

        [void]$cmd.Parameters.AddWithValue("@order_no", $orderNo)
        [void]$cmd.Parameters.AddWithValue("@sold_at", $soldAt)
        [void]$cmd.Parameters.AddWithValue("@store_name", $storeName)
        [void]$cmd.Parameters.AddWithValue("@total_amount", $totalAmount)
        [void]$cmd.Parameters.AddWithValue("@barcode", $barcode)
        [void]$cmd.Parameters.AddWithValue("@style_no", $styleNo)
        [void]$cmd.Parameters.AddWithValue("@unit_price", $unitPrice)
        [void]$cmd.Parameters.AddWithValue("@brand", $(if ($brand) { $brand } else { [DBNull]::Value }))
        [void]$cmd.Parameters.AddWithValue("@category", $(if ($category) { $category } else { [DBNull]::Value }))
        [void]$cmd.Parameters.AddWithValue("@image_url", $(if ($imageUrl) { $imageUrl } else { [DBNull]::Value }))
        [void]$cmd.ExecuteNonQuery()
        $importedCount++
    }

    $transaction.Commit()
    Write-Host "Imported rows: $importedCount" -ForegroundColor Green
    if ($skippedEmptyRows -gt 0) {
        Write-Host "Skipped empty rows: $skippedEmptyRows" -ForegroundColor Yellow
    }
}
catch {
    $transaction.Rollback()
    throw
}
finally {
    $connection.Close()
}
