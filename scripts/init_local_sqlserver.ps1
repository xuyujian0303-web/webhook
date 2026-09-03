param(
    [string]$Server = "localhost"
)

Add-Type -AssemblyName System.Data

function Invoke-SqlNonQuery {
    param(
        [string]$ConnectionString,
        [string]$Sql
    )

    $connection = New-Object System.Data.SqlClient.SqlConnection $ConnectionString
    $connection.Open()
    try {
        $command = $connection.CreateCommand()
        $command.CommandText = $Sql
        [void]$command.ExecuteNonQuery()
    }
    finally {
        $connection.Close()
    }
}

$masterConnection = "Server=$Server;Database=master;Integrated Security=True;TrustServerCertificate=True;"

Invoke-SqlNonQuery -ConnectionString $masterConnection -Sql @"
IF DB_ID(N'wecom_bot_app') IS NULL
    CREATE DATABASE [wecom_bot_app];
IF DB_ID(N'wecom_sales_test') IS NULL
    CREATE DATABASE [wecom_sales_test];
"@

$salesConnection = "Server=$Server;Database=wecom_sales_test;Integrated Security=True;TrustServerCertificate=True;"

Invoke-SqlNonQuery -ConnectionString $salesConnection -Sql @"
IF OBJECT_ID(N'dbo.sales_lines', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.sales_lines (
        id INT IDENTITY(1,1) PRIMARY KEY,
        order_no NVARCHAR(64) NOT NULL,
        sold_at DATETIME2 NOT NULL,
        store_name NVARCHAR(32) NOT NULL,
        total_amount DECIMAL(18, 2) NOT NULL,
        barcode NVARCHAR(64) NOT NULL,
        style_no NVARCHAR(32) NOT NULL,
        unit_price DECIMAL(18, 2) NOT NULL,
        brand NVARCHAR(64) NULL,
        category NVARCHAR(64) NULL,
        image_url NVARCHAR(512) NULL
    );
END;

DELETE FROM dbo.sales_lines;

INSERT INTO dbo.sales_lines (order_no, sold_at, store_name, total_amount, barcode, style_no, unit_price, brand, category, image_url) VALUES
(N'SOG609260605001', '2026-06-05T10:50:00', N'G609', 21500.00, N'GDRCH042ACBK0B6360009', N'DRCH042ABK0', 14500.00, N'Dazzle', N'Coat', N'https://img.example.com/DRCH042ABK0.jpg'),
(N'SOG609260605001', '2026-06-05T10:50:00', N'G609', 21500.00, N'GJACH029ACOW0B6420001', N'JACH029AOW0', 3000.00, N'Dazzle', N'Accessory', N'https://img.example.com/JACH029AOW0.jpg'),
(N'SOG609260605001', '2026-06-05T10:50:00', N'G609', 21500.00, N'GSKCH175ACWH0B6380011', N'SKCH175AWH0', 4000.00, N'Dazzle', N'Sneaker', N'https://img.example.com/SKCH175AWH0.jpg'),
(N'XSG83C260626001', '2026-06-26T12:19:00', N'G830', 82280.00, N'GCOCF690AIEC0C5360005', N'COCF690AEC0', 93500.00, N'Dazzle', N'Coat', N'https://img.example.com/COCF690AEC0.jpg');
"@

Write-Output "Initialized SQL Server databases: wecom_bot_app, wecom_sales_test"
Write-Output "Seeded table: wecom_sales_test.dbo.sales_lines"
