def hex_to_decimal_uid():
    hex_uid = input("Voer de hex UID in (zonder spaties, bv. 04A2B3C4): ").strip()
    
    try:
        # Normale conversie
        dec = int(hex_uid, 16)

        # Bytes opdelen en omdraaien
        bytes_list = [hex_uid[i:i+2] for i in range(0, len(hex_uid), 2)]
        rev_hex = "".join(reversed(bytes_list))
        dec_rev = int(rev_hex, 16)

        print(f"\nHex UID: {hex_uid}")
        print(f"Decimaal (normaal): {dec}")
        print(f"Decimaal (reversed bytes): {dec_rev}")

    except ValueError:
        print("Ongeldige invoer! Zorg dat je alleen hex-tekens (0–9, A–F) gebruikt.")

if __name__ == "__main__":
    hex_to_decimal_uid()