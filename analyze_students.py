# -*- coding: utf-8 -*-
import pandas as pd
import json
import sys
import io

# Set UTF-8 for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

df = pd.read_excel('data/student_dataset.xlsx')
print("Columns:", df.columns.tolist())
print("Shape:", df.shape)
print("Data types:", df.dtypes.to_dict())

# Save sample to JSON to avoid encoding issues in console
sample = df.head(20).to_dict(orient='records')
with open('data/student_sample.json', 'w', encoding='utf-8') as f:
    json.dump(sample, f, ensure_ascii=False, indent=2, default=str)
print("Sample saved to data/student_sample.json")
