import pricing
text = "0-4.4\t0.80\n4.41-10\t0.80\n10.01-22\t1.20\n\u226450lbs\t1.50\n150.01+\t3.00"
result = pricing.parse_outbound_paste(text)
for t in result:
    hi = "inf" if t["max_lbs"] >= 9999 else str(t["max_lbs"])
    print(f"{t['min_lbs']}-{hi}  ${t['price']}")
print(f"\nTotal: {len(result)} tiers")
