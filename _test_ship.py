import pricing

text = "Weight\tZone2\tZone3\tZone4\n1\t34.00\t22.00\t18.00\n2\t56.00\t35.00\t28.00\n5\t7.00\t5.50\t4.80"
result = pricing.parse_shipping_paste(text)
print("carrier:", repr(result["carrier"]))
for zn in sorted(result["zones"].keys()):
    print(zn, result["zones"][zn])

# with # carrier meta line
text2 = "# carrier FedEx\nWeight\tZone2\tZone3\tZone4\n1\t34.00\t22.00\t18.00\n2\t56.00\t35.00\t28.00"
result2 = pricing.parse_shipping_paste(text2)
print("\ncarrier2:", repr(result2["carrier"]))
print("Zone2:", result2["zones"]["Zone2"])
