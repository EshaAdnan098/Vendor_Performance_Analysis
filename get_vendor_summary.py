import pandas as pd
import sqlite3
import logging
from ingestion_db import ingest_db

# ---------------------------
# 1. Configure Logging
# ---------------------------
logging.basicConfig(
    filename="logs/get_vendor_summary.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)

# ---------------------------
# 2. Utility Functions
# ---------------------------
def connect_db(db_path="inventory.db"):
    """Create a SQLite database connection."""
    return sqlite3.connect(db_path)

def create_vendor_summary(conn):
    """Create a vendor sales summary by combining purchases, sales, and freight."""
    vendor_sales_summary = pd.read_sql_query("""
    WITH FreightSummary AS (
        SELECT
            VendorNumber,
            SUM(Freight) AS FreightCost
        FROM vendor_invoice
        GROUP BY VendorNumber
    ),

    PurchaseSummary AS (
        SELECT
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.PurchasePrice,
            p.Description,
            pp.Volume,
            pp.Price AS ActualPrice,
            SUM(p.Quantity) AS TotalPurchaseQuantity,
            SUM(p.Dollars) AS TotalPurchaseDollars
        FROM purchases p
        JOIN purchase_prices pp
            ON p.Brand = pp.Brand
        WHERE p.PurchasePrice > 0
        GROUP BY p.VendorNumber, p.VendorName, p.Brand, p.Description, 
                 p.PurchasePrice, pp.Price, pp.Volume
    ),

    SalesSummary AS (
        SELECT
            VendorNo,
            Brand,
            SUM(SalesDollars) AS TotalSalesDollars,
            SUM(SalesPrice) AS TotalSalesPrice,
            SUM(SalesQuantity) AS TotalSalesQuantity,
            SUM(ExciseTax) AS TotalExciseTax
        FROM sales
        GROUP BY VendorNo, Brand
    )

    SELECT
        ps.VendorNumber,
        ps.VendorName,
        ps.Brand,
        ps.Description,
        ps.PurchasePrice,
        ps.ActualPrice,
        ps.Volume,
        ps.TotalPurchaseQuantity,
        ps.TotalPurchaseDollars,
        ss.TotalSalesQuantity,
        ss.TotalSalesDollars,
        ss.TotalSalesPrice,
        ss.TotalExciseTax,
        fs.FreightCost
    FROM PurchaseSummary ps
    LEFT JOIN SalesSummary ss
        ON ps.VendorNumber = ss.VendorNo
       AND ps.Brand = ss.Brand
    LEFT JOIN FreightSummary fs
        ON ps.VendorNumber = fs.VendorNumber
    ORDER BY ps.TotalPurchaseDollars DESC
    """, conn)
    
    return vendor_sales_summary

def clean_data(df):
    """Clean the data and create new calculated columns."""
    
    # --- Changing datatype ---
    df['Volume'] = df['Volume'].astype('float')

    # --- Fill missing values with 0 ---
    df.fillna(0, inplace=True)

    # --- Remove extra spaces from text columns ---
    df['VendorName'] = df['VendorName'].str.strip()
    df['Description'] = df['Description'].str.strip()

    # --- Create new calculated columns ---
    df['GrossProfit'] = df['TotalSalesDollars'] - df['TotalPurchaseDollars']
    df['ProfitMargin'] = (df['GrossProfit'] / df['TotalSalesDollars']) * 100
    df['StockTurnover'] = df['TotalSalesQuantity'] / df['TotalPurchaseQuantity']
    df['SalesToPurchaseRatio'] = df['TotalSalesDollars'] / df['TotalPurchaseDollars']

    return df

# ---------------------------
# 3. Main script
# ---------------------------
if __name__ == '__main__':
    # creating database connection
    conn = sqlite3.connect('inventory.db')

    logging.info('Creating Vendor Summary Table.....')
    summary_df = create_vendor_summary(conn)
    logging.info("\n" + summary_df.head().to_string())

    logging.info('Cleaning Data.....')
    clean_df = clean_data(summary_df)
    logging.info("\n" + clean_df.head().to_string())

    logging.info('Ingesting data.....')
    ingest_db(clean_df, 'vendor_sales_summary', conn)

    logging.info('Completed')

vendor_sales_summary.to_csv("data/vendor_sales_summary.csv", index=False)
