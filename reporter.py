import pandas as pd
from tabulate import tabulate


class Reporter:
    def __init__(self, transactions: list, source_file: str = ""):
        self.transactions = transactions
        self.source_file = source_file
        self.df = self._build_df()

    def _build_df(self) -> pd.DataFrame:
        if not self.transactions:
            return pd.DataFrame(columns=[
                "date", "value_date", "description",
                "debit", "credit", "balance"
            ])
        df = pd.DataFrame(self.transactions)
        # Ensure all expected columns exist
        for col in ["date", "value_date", "description", "debit", "credit", "balance"]:
            if col not in df.columns:
                df[col] = ""
        # Convert numeric columns
        for col in ["debit", "credit", "balance"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df[["date", "value_date", "description", "debit", "credit", "balance"]]

    def print_summary(self):
        df = self.df
        total_debit  = df["debit"].sum()
        total_credit = df["credit"].sum()
        net          = total_credit - total_debit
        closing      = df["balance"].iloc[-1] if not df.empty else 0.0
        direction    = "surplus" if net >= 0 else "deficit"

        print("\n" + "=" * 60)
        print("  TRANSACTION TABLE")
        print("=" * 60)
        if not df.empty:
            display_df = df.copy()
            for col in ["debit", "credit", "balance"]:
                display_df[col] = display_df[col].apply(
                    lambda x: f"N {x:,.2f}" if x != 0 else ""
                )
            print(tabulate(
                display_df,
                headers="keys",
                tablefmt="rounded_outline",
                showindex=False,
                maxcolwidths=[12, 12, 40, 14, 14, 14]
            ))
        else:
            print("  No transactions found.")

        print("\n" + "=" * 60)
        print("  FINANCIAL SUMMARY")
        print("=" * 60)
        print(f"  Source File    : {self.source_file}")
        print(f"  Total Rows     : {len(df)}")
        print(f"  Debit Rows     : {(df['debit'] > 0).sum()}")
        print(f"  Credit Rows    : {(df['credit'] > 0).sum()}")
        print(f"  Total Debits   : N {total_debit:,.2f}")
        print(f"  Total Credits  : N {total_credit:,.2f}")
        print(f"  Net Cash Flow  : N {abs(net):,.2f} ({direction})")
        print(f"  Closing Balance: N {closing:,.2f}")
        print("=" * 60)

    def save_excel(self, path: str):
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.df.to_excel(writer, index=False, sheet_name="Transactions")
            # Auto-fit column widths
            ws = writer.sheets["Transactions"]
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col) + 4
                ws.column_dimensions[col[0].column_letter].width = min(max_len, 60)

    def save_csv(self, path: str):
        self.df.to_csv(path, index=False)
