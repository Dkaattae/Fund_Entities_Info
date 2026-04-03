import pandas as pd

df = pd.read_csv("LawyerList.csv")
df_unique = df.drop_duplicates(subset="lawyer_id")
print(len(df_unique))  # should be close to 189
df_unique.to_csv("lawyers_dedup.csv", index=False)