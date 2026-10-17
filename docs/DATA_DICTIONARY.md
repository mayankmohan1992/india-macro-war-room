<!-- GENERATED FILE - produced by tools/gen_docs.py from the built dataset. Do not edit by hand: the next refresh overwrites it. -->

# Data dictionary

**38 indicators** · dataset as-of **2026-10-06** · generated 2026-10-17 21:47 IST

Every series is derived from a published RBI table; `kind` distinguishes a policy **setting** (a rate that changes occasionally, dated by when it took effect) from a **reading** (an observation dated by the period it covers). Values are in the unit shown; growth rates are year-on-year per cent unless stated otherwise.

Machine-readable equivalents: `api/v1/index.json` (catalogue), `api/v1/series/<id>.json` (full history), `api/v1/series/<id>.csv` (CSV).


## Credit

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cdr` | Credit-to-deposit ratio | % | reading | fortnightly | 80.98 | 2026-09-30 | RBI r9 | [Credit-deposit ratio (outstanding and incremental)](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `credit` | Bank credit growth | % | reading | fortnightly | 19.38 | 2026-09-30 | RBI r9 | [Bank credit of scheduled commercial banks](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `deposit` | Aggregate deposit growth | % | reading | fortnightly | 17.83 | 2026-09-30 | RBI r9 | [Aggregate deposits with scheduled commercial banks](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |
| `food` | Food credit growth | % | reading | fortnightly | 125.71 | 2026-09-30 | RBI r9 | [Food credit (procurement credit to FCI and state agencies)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `invest` | SCB investments growth | % | reading | fortnightly | 8.64 | 2026-09-30 | RBI r9 | [Bank investments in government and other approved securities](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `nonfood` | Non-food credit growth | % | reading | fortnightly | 19.15 | 2026-09-30 | RBI r9 | [Bank credit of scheduled commercial banks](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |

## External

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `fca` | RBI foreign currency assets | % | reading | weekly | 13.37 | 2026-10-02 | RBI r39 | [Foreign Currency Assets (FCA) and India's foreign exchange reserves](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `fwd3m` | 3-month US$ forward premia | % | reading | weekly | 4.31 | 2026-10-02 | RBI r10 (weekly WSS) | [US dollar forward premia (1, 3 and 6 months), per cent per annum](https://www.fbil.org.in/uploads/REVISED_ETHODOLOGY_FOR_FORWARD_PREMIA_AND_MIFOR_CURVE_4b25a32468.pdf) |
| `fxa` | Net FX assets (banking sector) | % | reading | fortnightly | 15.17 | 2026-09-30 | RBI r13 | [Net foreign exchange assets of the banking sector](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `gold` | RBI gold holdings | % | reading | weekly | 16.85 | 2026-10-02 | RBI r39 | [RBI gold holdings (gold component of the reserves)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `usdinr` | USD/INR | ₹ | reading | weekly | 95.99 | 2026-10-02 | RBI r10 (weekly WSS) | [USD/INR and EUR/INR spot exchange rates (Reference Rate)](https://www.fbil.org.in/securities?mq=o&op=referencerate) |

## Fiscal

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `rbicredit` | RBI credit to the Centre | ₹ crore | reading | weekly | 93,392 *(stale)* | 2026-04-17 | RBI r39 | [RBI loans and advances to the Central Government](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `rupeesec` | RBI rupee securities | % | reading | weekly | 23.67 | 2026-10-02 | RBI r39 | [RBI rupee securities (including treasury bills)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `tbill` | T-bill outstanding | ₹ crore | reading | weekly | 819,581 | 2026-10-02 | RBI r2 | [Treasury bills (91-day, 182-day, 364-day) and Cash Management Bills](https://rbi.org.in/scripts/FS_FAQs.aspx?Id=79) |

## Liquidity

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `bankdep` | Bankers' deposits with RBI | % | reading | weekly | 2.87 | 2026-10-02 | RBI r39 | [Bankers' deposits with the Reserve Bank](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `liquidity` | Liquidity (1-month avg net ops) | ₹ crore | reading | daily | -278,308 | 2026-10-04 | RBI r8 | [Liquidity Adjustment Facility: net injection (+) / absorption (-), SDF and MSF](https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=62917) |

## Markets

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cdout` | CD outstanding | ₹ crore | reading | fortnightly | 574,064 | 2026-09-30 | RBI r4 | [Certificate of Deposit (CD)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12108) |
| `cpout` | Commercial paper outstanding | ₹ crore | reading | fortnightly | 621,596 | 2026-09-30 | RBI r5 | [Commercial Paper (CP)](https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12592) |
| `gsec` | 10-year G-sec yield | % | reading | weekly | 7.23 | 2026-10-02 | RBI r10 | [10-year Government of India benchmark G-Sec par yield (FBIL)](https://www.fbil.org.in/uploads/Newsletter_for_the_month_of_April_2024_ea8fe6cc8f.pdf) |
| `termspread` | Term spread (10y − 91d) | pp | reading | weekly | 1.71 | 2026-10-02 | derived (r10) | [Term spread (10-year G-sec par yield − 91-day T-bill yield)](https://www.rbi.org.in/Scripts/WSSView.aspx?Id=28379) |
| `turnover` | Money-market turnover | ₹ crore | reading | weekly | 1,850,297 | 2026-10-02 | RBI r12 | [Money-market turnover (call, notice/term money, triparty repo, market repo)](https://www.rbi.org.in/Scripts/WSSView.aspx?Id=28379) |
| `yld91` | 91-day T-bill yield | % | reading | weekly | 5.52 | 2026-10-02 | RBI r10 (weekly WSS) | [Treasury bills (91-day, 182-day, 364-day) and Cash Management Bills](https://rbi.org.in/scripts/FS_FAQs.aspx?Id=79) |

## Money

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `m1` | M1 (narrow money) growth | % | reading | fortnightly | 17.01 | 2026-09-30 | RBI r13 | [M1 / narrow money](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `m3` | M3 (broad money) growth | % | reading | fortnightly | 16.86 | 2026-09-30 | RBI r13 | [M3 / broad money](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `moneymult` | Money multiplier | x | reading | fortnightly | 6.4 | 2026-09-30 | derived (r13 ÷ r7) | [Money multiplier (M3 ÷ reserve money)](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `notes` | Notes in circulation growth | % | reading | weekly | 13.4 | 2026-10-02 | RBI r39 | [Notes in circulation](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `rm` | Reserve money growth | % | reading | weekly | 8.69 | 2026-09-30 | RBI r7 | [Reserve money / base money (M0)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |

## Policy

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `callmoney` | Call money rate | % | reading | weekly | 5.12 | 2026-10-02 | RBI r10 | [Call money rate (weighted average)](https://rbi.org.in/scripts/publicationsView.aspx?id=15762) |
| `crr` | Cash Reserve Ratio | % | setting | weekly | 3 | 2026-10-02 | RBI r10 | [Cash Reserve Ratio (CRR)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |
| `repo` | Policy repo rate | % | setting | weekly | 5.5 | 2026-10-06 | DBIE key rates | [Policy repo rate](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/jun/doc202566565201.pdf) |
| `slr` | Statutory Liquidity Ratio | % | setting | weekly | 18 | 2026-10-02 | RBI r10 | [Statutory Liquidity Ratio (SLR)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |

## Prices

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cpi` | CPI inflation | % | reading | monthly | 4.82 | 2026-08-31 | RBI r11 (CPI 2024=100) | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `cpirural` | CPI rural | % | reading | monthly | 5.3 | 2026-08-31 | RBI r11 | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `cpiurban` | CPI urban | % | reading | monthly | 4.34 | 2026-08-31 | RBI r11 | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `wpi` | WPI inflation | % | reading | monthly | 11.39 | 2026-09-30 | RBI r11 (WPI 2023=100) | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpifuel` | WPI fuel & power | % | reading | monthly | 25.85 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpimanu` | WPI manufactured products | % | reading | monthly | 9.76 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpiprim` | WPI primary articles | % | reading | monthly | 8.67 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
