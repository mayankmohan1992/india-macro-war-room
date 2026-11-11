<!-- GENERATED FILE - produced by tools/gen_docs.py from the built dataset. Do not edit by hand: the next refresh overwrites it. -->

# Data dictionary

**45 indicators** · dataset as-of **2026-11-01** · generated 2026-11-11 13:36 IST

Every series is derived from a published RBI table; `kind` distinguishes a policy **setting** (a rate that changes occasionally, dated by when it took effect) from a **reading** (an observation dated by the period it covers). Values are in the unit shown; growth rates are year-on-year per cent unless stated otherwise.

Machine-readable equivalents: `api/v1/index.json` (catalogue), `api/v1/series/<id>.json` (full history), `api/v1/series/<id>.csv` (CSV).


## Activity

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `gva` | GVA growth, y-o-y (computed) | % | reading | quarterly | 8.23 | 2026-04-01 | MoSPI NAS quarterly (computed from published levels) | [Gross Value Added (GVA) at basic prices, constant prices](https://esankhyiki.mospi.gov.in/macroindicators?product=nas) |
| `iip` | IIP growth, y-o-y | % | reading | monthly | 6.7 | 2026-09-01 | MoSPI IIP monthly | [Index of Industrial Production (IIP), General — base 2022-23](https://esankhyiki.mospi.gov.in/macroindicators?product=iip) |
| `iipcap` | IIP capital goods growth, y-o-y | % | reading | monthly | 10.4 | 2026-09-01 | MoSPI IIP monthly, use-based: Capital Goods | [Index of Industrial Production — use-based classification](https://esankhyiki.mospi.gov.in/macroindicators?product=iip) |
| `lfpr` | Labour force participation (15+) | % | reading | monthly | 55.5 | 2026-09-01 | MoSPI PLFS monthly (CWS), both | [Labour Force Participation Rate (LFPR)](https://esankhyiki.mospi.gov.in/macroindicators?product=plfs) |
| `oppi` | Producer price inflation, y-o-y | % | reading | monthly | 9.81 | 2026-08-01 | MoSPI OPPI monthly (computed from published levels) | [Producer Price Index (OPPI), all commodities — base 2022-23](https://esankhyiki.mospi.gov.in/macroindicators?product=oppi) |
| `ur` | Unemployment rate (15+) | % | reading | monthly | 5 | 2026-09-01 | MoSPI PLFS monthly (CWS), both | [Unemployment Rate (UR), Periodic Labour Force Survey — current weekly status](https://esankhyiki.mospi.gov.in/macroindicators?product=plfs) |
| `wpr` | Worker population ratio (15+) | % | reading | monthly | 52.7 | 2026-09-01 | MoSPI PLFS monthly (CWS), both | [Worker Population Ratio (WPR)](https://esankhyiki.mospi.gov.in/macroindicators?product=plfs) |

## Credit

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cdr` | Credit-to-deposit ratio | % | reading | fortnightly | 81.59 | 2026-10-15 | RBI r9 | [Credit-deposit ratio (outstanding and incremental)](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `credit` | Bank credit growth | % | reading | fortnightly | 18.23 | 2026-10-15 | RBI r9 | [Bank credit of scheduled commercial banks](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `deposit` | Aggregate deposit growth | % | reading | fortnightly | 16.72 | 2026-10-15 | RBI r9 | [Aggregate deposits with scheduled commercial banks](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |
| `food` | Food credit growth | % | reading | fortnightly | 90.69 | 2026-10-15 | RBI r9 | [Food credit (procurement credit to FCI and state agencies)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `invest` | SCB investments growth | % | reading | fortnightly | 9.49 | 2026-10-15 | RBI r9 | [Bank investments in government and other approved securities](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `nonfood` | Non-food credit growth | % | reading | fortnightly | 18.03 | 2026-10-15 | RBI r9 | [Bank credit of scheduled commercial banks](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |

## External

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `fca` | RBI foreign currency assets | % | reading | weekly | 11.84 | 2026-10-30 | RBI r39 | [Foreign Currency Assets (FCA) and India's foreign exchange reserves](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `fwd3m` | 3-month US$ forward premia | % | reading | weekly | 5.35 | 2026-10-30 | RBI r10 (weekly WSS) | [US dollar forward premia (1, 3 and 6 months), per cent per annum](https://www.fbil.org.in/uploads/REVISED_ETHODOLOGY_FOR_FORWARD_PREMIA_AND_MIFOR_CURVE_4b25a32468.pdf) |
| `fxa` | Net FX assets (banking sector) | % | reading | fortnightly | 14.82 | 2026-10-15 | RBI r13 | [Net foreign exchange assets of the banking sector](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `gold` | RBI gold holdings | % | reading | weekly | 7.87 | 2026-10-30 | RBI r39 | [RBI gold holdings (gold component of the reserves)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `usdinr` | USD/INR | ₹ | reading | weekly | 95.25 | 2026-10-30 | RBI r10 (weekly WSS) | [USD/INR and EUR/INR spot exchange rates (Reference Rate)](https://www.fbil.org.in/securities?mq=o&op=referencerate) |

## Fiscal

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `rbicredit` | RBI credit to the Centre | ₹ crore | reading | weekly | 93,392 *(stale)* | 2026-04-17 | RBI r39 | [RBI loans and advances to the Central Government](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `rupeesec` | RBI rupee securities | % | reading | weekly | 21.3 | 2026-10-30 | RBI r39 | [RBI rupee securities (including treasury bills)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `tbill` | T-bill outstanding | ₹ crore | reading | weekly | 784,548 | 2026-10-30 | RBI r2 | [Treasury bills (91-day, 182-day, 364-day) and Cash Management Bills](https://rbi.org.in/scripts/FS_FAQs.aspx?Id=79) |

## Liquidity

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `bankdep` | Bankers' deposits with RBI | % | reading | weekly | 0.61 | 2026-10-30 | RBI r39 | [Bankers' deposits with the Reserve Bank](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `liquidity` | Liquidity (1-month avg net ops) | ₹ crore | reading | daily | -143,546.227 | 2026-11-01 | RBI r8 | [Liquidity Adjustment Facility: net injection (+) / absorption (-), SDF and MSF](https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=62917) |

## Markets

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cdout` | CD outstanding | ₹ crore | reading | fortnightly | 594,204 | 2026-10-31 | RBI r4 | [Certificate of Deposit (CD)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12108) |
| `cpout` | Commercial paper outstanding | ₹ crore | reading | fortnightly | 661,259 | 2026-10-31 | RBI r5 | [Commercial Paper (CP)](https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12592) |
| `gsec` | 10-year G-sec yield | % | reading | weekly | 7.45 | 2026-10-30 | RBI r10 | [10-year Government of India benchmark G-Sec par yield (FBIL)](https://www.fbil.org.in/uploads/Newsletter_for_the_month_of_April_2024_ea8fe6cc8f.pdf) |
| `termspread` | Term spread (10y − 91d) | pp | reading | weekly | 1.52 | 2026-10-30 | derived (r10) | [Term spread (10-year G-sec par yield − 91-day T-bill yield)](https://www.rbi.org.in/Scripts/WSSView.aspx?Id=28379) |
| `turnover` | Money-market turnover | ₹ crore | reading | weekly | 1,857,855 | 2026-10-30 | RBI r12 | [Money-market turnover (call, notice/term money, triparty repo, market repo)](https://www.rbi.org.in/Scripts/WSSView.aspx?Id=28379) |
| `yld91` | 91-day T-bill yield | % | reading | weekly | 5.93 | 2026-10-30 | RBI r10 (weekly WSS) | [Treasury bills (91-day, 182-day, 364-day) and Cash Management Bills](https://rbi.org.in/scripts/FS_FAQs.aspx?Id=79) |

## Money

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `m1` | M1 (narrow money) growth | % | reading | fortnightly | 12.56 | 2026-10-15 | RBI r13 | [M1 / narrow money](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `m3` | M3 (broad money) growth | % | reading | fortnightly | 15.97 | 2026-10-15 | RBI r13 | [M3 / broad money](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `moneymult` | Money multiplier | x | reading | fortnightly | 6.25 | 2026-10-15 | derived (r13 ÷ r7) | [Money multiplier (M3 ÷ reserve money)](https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=17618) |
| `notes` | Notes in circulation growth | % | reading | weekly | 14.18 | 2026-10-30 | RBI r39 | [Notes in circulation](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |
| `rm` | Reserve money growth | % | reading | weekly | 10.33 | 2026-10-15 | RBI r7 | [Reserve money / base money (M0)](https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/HWSSF170614.pdf) |

## Policy

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `callmoney` | Call money rate | % | reading | weekly | 5.69 | 2026-10-30 | RBI r10 | [Call money rate (weighted average)](https://rbi.org.in/scripts/publicationsView.aspx?id=15762) |
| `crr` | Cash Reserve Ratio | % | setting | weekly | 3 | 2026-10-30 | RBI r10 | [Cash Reserve Ratio (CRR)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |
| `repo` | Policy repo rate | % | setting | weekly | 5.5 | 2026-10-30 | RBI r10 (weekly WSS) | [Policy repo rate](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/jun/doc202566565201.pdf) |
| `slr` | Statutory Liquidity Ratio | % | setting | weekly | 18 | 2026-10-30 | RBI r10 | [Statutory Liquidity Ratio (SLR)](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12131) |

## Prices

| id | indicator | unit | kind | frequency | latest | as at | source table | definition |
|---|---|---|---|---|---:|---|---|---|
| `cpi` | CPI inflation | % | reading | monthly | 5.54 | 2026-09-30 | RBI DBIE indicator series (RBIB18) | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `cpirural` | CPI rural | % | reading | monthly | 6.07 | 2026-09-30 | RBI r11 | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `cpiurban` | CPI urban | % | reading | monthly | 4.82 | 2026-09-30 | RBI r11 | [Consumer Price Index (CPI) inflation, combined](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051&lang=1&reg=48) |
| `wpi` | WPI inflation | % | reading | monthly | 11.39 | 2026-09-30 | RBI r11 (WPI 2023=100) | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpifuel` | WPI fuel & power | % | reading | monthly | 25.85 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpimanu` | WPI manufactured products | % | reading | monthly | 9.76 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
| `wpiprim` | WPI primary articles | % | reading | monthly | 8.67 | 2026-09-30 | RBI r11 | [Wholesale Price Index (WPI) inflation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2272872&lang=2&reg=48) |
