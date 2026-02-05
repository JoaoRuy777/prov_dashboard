import pandas as pd
from src.database import get_data
from src.processing import process_data, filter_data

def test_pipeline():
    print("Testing Pipeline...")
    
    # 1. Get Data
    df = get_data(use_mock=True)
    print(f"Data Fetched: {len(df)} rows")
    assert not df.empty, "DataFrame should not be empty"
    
    # 2. Process Data
    processed_df = process_data(df)
    print("Data Processed.")
    assert 'treated_error' in processed_df.columns, "treated_error column missing"
    
    # 3. Filter Data (Simulate UI interaction)
    filtered_df = filter_data(processed_df, status_filter=['Error'], type_filter=None, date_range=None)
    print(f"Filtered (Errors only): {len(filtered_df)} rows")
    
    if not filtered_df.empty:
        example_error = filtered_df.iloc[0]['treated_error']
        print(f"Example Error Treatment: {filtered_df.iloc[0]['raw_error']} -> {example_error}")
        
    print("Backend Logic Verified Successfully.")

if __name__ == "__main__":
    test_pipeline()
