Control 3 - Customer/Merchant Performance

PAIR - Intake

Exported on 2026-06-03 07:52:46

# Table of Contents

1 Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another [4](#control-3.1-mastercard-may-not-disclose-information-about-the-performance-of-one-entity-to-another)

1.1 Delivering Metrics and Insights to Merchants [4](#delivering-metrics-and-insights-to-merchants)

1.2 Interchange metrics [5](#interchange-metrics)

2 Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds [7](#control-3.2-benchmarked-analytics-must-meet-certain-thresholds)

2.1 Examples of Compliant Benchmark Groups [8](#examples-of-compliant-benchmark-groups)

2.1.1 Merchant Benchmark Examples [8](#merchant-benchmark-examples)

2.1.2 Issuer Benchmark Concentration Rule Examples [9](#issuer-benchmark-concentration-rule-examples)

2.2 Potential Solutions for Non-Compliant Benchmark Groups [9](#potential-solutions-for-non-compliant-benchmark-groups)

2.3 Handling Issuer Requests for Top Merchants [13](#handling-issuer-requests-for-top-merchants)

2.4 Malls and Retail Parks [14](#malls-and-retail-parks)

2.5 Sample Q&A with Clients [15](#sample-qa-with-clients)

2.6 Best in Class Metrics [15](#best-in-class-metrics)

3 Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client [17](#control-3.3-mastercard-may-not-disclose-any-information-about-the-composition-of-a-peer-group-or-category-to-a-client)

4 Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review [18](#control-3.4-metrics-about-a-mobile-payment-or-digital-wallet-providers-performance-and-metrics-reported-to-mobile-payment-or-digital-wallet-providers-require-case-by-case-privacy-review)

**CONFIDENTIAL / NOT FOR EXTERNAL DISTRIBUTION**

- [Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another](#control-3.1-mastercard-may-not-disclose-information-about-the-performance-of-one-entity-to-another)

  - [Delivering Metrics and Insights to Merchants](#delivering-metrics-and-insights-to-merchants)

  - [Interchange metrics](#interchange-metrics)

- [Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds](#control-3.2-benchmarked-analytics-must-meet-certain-thresholds)

  - [Examples of Compliant Benchmark Groups](#examples-of-compliant-benchmark-groups)

    - [Merchant Benchmark Examples](#merchant-benchmark-examples)

    - [Issuer Benchmark Concentration Rule Examples](#issuer-benchmark-concentration-rule-examples)

  - [Potential Solutions for Non-Compliant Benchmark Groups](#potential-solutions-for-non-compliant-benchmark-groups)

  - [Handling Issuer Requests for Top Merchants](#handling-issuer-requests-for-top-merchants)

  - [Malls and Retail Parks](#malls-and-retail-parks)

  - [Sample Q&A with Clients](#sample-qa-with-clients)

  - [Best in Class Metrics](#best-in-class-metrics)

- [Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client](#control-3.3-mastercard-may-not-disclose-any-information-about-the-composition-of-a-peer-group-or-category-to-a-client)

- [Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review](#control-3.4-metrics-about-a-mobile-payment-or-digital-wallet-providers-performance-and-metrics-reported-to-mobile-payment-or-digital-wallet-providers-require-case-by-case-privacy-review)

The controls below are intended to protect the confidentiality of client and merchant performance data by, for example, applying benchmarking rules, preserving the confidentiality/composition of peer groups, and adhering to contractual obligations. 

Please note that information exchange and competition laws are an evolving area. The controls below, by themselves, may not always be sufficient to protect against anti-competitive activity. In some circumstances, it may be necessary for product teams to work with competition law counsel, Data Strategy, and Privacy to apply additional or alternative controls where appropriate.

For questions, please create an [Intake Brief](https://confluence.mastercard.int/pages/viewpage.action?pageId=849582763) and contact the member of the Privacy team responsible for your region.

**Critical Notes**

- **You may not report <u>digital wallet</u> metrics without Privacy approval. See Control 3.4. **

- **You may not create a deliverable that includes a list of “<u>top merchants</u>,” even if you mask the identity of individual merchants.**

- **<u>Market share</u> analyses (e.g., an analysis of an entire geographic region, country, MCC, or industry) are a type of benchmark analysis that can be sensitive from a competition and investor relations perspective. Market share metrics must comply with Controls 3 and 4.**

- **When including <u>Citibank</u> in a peer group (i.e., when a Citi competitor is to receive the output), the peer group must meet one of the above rules, but Citi may only represent a maximum of 25% of the peer group even if 6/30, 7/35, or 10/40 are used.**

# Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another

Mastercard’s transaction data can be used to assess the performance of a variety of stakeholders in the payments ecosystem. In many cases, clients want insights into their own performance as well as the performance of their competitors, partners, subsidiaries, or other third parties. Mastercard cannot provide insights that are indicative of one entity’s performance to another entity unless the entity or entities whose performance is being disclosed provide their permission and the information sharing would not otherwise lead to anti-competitive effects (e.g., higher prices, reduced levels of service, coordination among competitors, etc.). If you have any doubts about whether the information sharing may lead to anti-competitive activity, please consult the Privacy or legal teams.

Use cases that **require** legal review include where we provide or create:

- An issuer’s co-brand portfolio metrics to the co-brand partner. Note: Delivering co-brand metrics to the co-brand merchant requires Mastercard to obtain a consent letter from the co-brand card issuer. This is because the disclosure of co-brand metrics to the merchant represents the confidential performance information of the co-brand issuer. 

- Spend metrics about merchants in a mall to the mall owner.

- Metrics to a publisher that measure the performance of specific merchant campaigns run on the publisher’s platform. A “publisher” is any entity that displays advertisements on its properties, e.g., a website owner or a sports stadium.

- An issuer’s portfolio spend metrics to a payment processor or program manager.

- Metrics about an entity’s performance to a potential buyer or its representatives in an M&A context.

- Metrics or a score about an entity, using transaction data pertaining to that entity, for evaluation purposes (e.g., to support lending decisions, invoicing or debt collection, etc.).

- A deliverable for a franchisor about a franchisee, or vice versa.

- Metrics to an aggregator or intermediary that resells our metrics to its client or combines our metrics with third-party data.

## Delivering Metrics and Insights to Merchants

Our ability to deliver metrics to merchants depends on the rules that apply to the sources of data we use to create those metrics.

If you are using, in whole or part, deidentified Mastercard transaction data (Data Warehouse data or cloud-hosted equivalent) to create metrics for merchants (which includes Digital Wallets in this context):

- <u>Default Rule</u>: You **must not** segment metrics that you deliver to merchants on a per-issuer or -acquirer basis without written permission from each issuer or acquirer, or explicit permission from the legal team. Written permission may be in the form of a contract, consent letter, or email. Please coordinate with the Product or Sales Legal team member supporting you.

- <u>Alternative Rule for Auth/Fraud Reports Only</u>:

  - This alternative is only available if (1) issuer authorization is practically infeasible, (2) the reports are designed to help the merchant troubleshoot payment authorization and/or fraud-related issues, **and** (3) the reports only rely on transaction data *already in the merchant’s possession.*

  - To use this alternative, you must include a representation from the merchant in the sales contract that it has access to the transaction data elements necessary for Mastercard to provide the analysis. We strongly recommend validating with the merchant beforehand that this representation is factual and accurate. The contract must specify the data elements that are in-scope at a level of detail that gives us reasonable assurance the merchant actually has that data.

  - An example of compliant contract language is below. You must validate this with Sales Legal counsel before proposing it to the client so that it can be properly customized and integrated into the agreement.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th style="text-align: left;"><blockquote>
<p>1. The following representations apply only with respect to Mastercard’s delivery of issuer-specific KPIs, metrics, or insights:  </p>
<p>1.1 Client represents and warrants that it possesses, or is entitled to receive from its acquiring bank, the following information for each transaction for the duration of the Term: BIN, BIN range, or issuer name; Decline reason codes; Authorization flag.  </p>
<p>1.2 Mastercard may request that Client represent (email sufficient) that it possesses, or is entitled to receive from its acquiring bank, additional data elements that are necessary to deliver customized issuer-specific metrics.  </p>
<p>1.3 If Client is unable to represent that it possesses, or is entitled to receive from its acquiring bank, the above-listed transaction data elements or additional data elements requested by Mastercard, Mastercard may, in its sole discretion, cease to provide issuer-specific metrics. </p>
</blockquote></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

If you are using solely merchant-supplied\* transaction, or other, data to deliver metrics to the merchant that supplied them:

- You **may** provide any segmentation of metrics. If those segmentations include segments that are issuer- or acquirer-specific, you must alert affected issuer or acquirer account teams before delivering such metrics.

- You **must** obtain review from PAIR if you plan to deliver individual-level metrics to the merchant.

\* In this context, "merchant-supplied" means data that is literally transferred from the merchant to Mastercard via SFTP, ShareFile, or some equivalent means. "Merchant-supplied" does **not** mean sourcing data from the Data Warehouse that is equivalent to the data available to the merchant.

You **must not** use data supplied by a merchant to perform an analysis for anyone other than that merchant unless you confirm that Mastercard obtained appropriate data use rights in the applicable contract with the merchant.

## Interchange metrics

You may provide interchange metrics to an issuer based on their own portfolio. 

 Interchange metrics **cannot** be delivered to a merchant due to the following reasons: 

- **Mastercard's framework protects confidentiality between acquirers and issuers: **Interchange is a fee between the acquirer and the issuer; the merchant does not know the amount. Merchant and acquirer independently negotiate the fee to be paid by merchant and Mastercard has not involvement in acquirer - merchant pricing. If we reveal the interchange fee of a specific transaction to a merchant, we are disclosing confidential information between the issuer and acquirer.   

- **It would expose issuer‑specific financial information: **If we provide granular interchange fees, the merchant can reverse engineer the rate back to a specific issuer. Revealing the fee would expose confidential business information about the issuer’s revenue stream and Mastercard’s fee structure.

As a result merchants could infer sensitive issuer economics, which would violate network rules and could lead to competitive misuse.

# Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds

If a client deliverable includes metrics that describe the performance of a group of third parties (i.e., entities that are not the client itself), Mastercard must obfuscate the performance of individual entities contained in those group metrics in a way that limits the client’s ability to discover or infer the identity or performance information of any individual entity in the group. Benchmarked analytics include:

- Market share analyses.

- Analyses of the performance of an MCC, industry, product type, geography, market, segment, or other category that includes transaction data of multiple issuers, acquirers, or merchants.

- Benchmarks that compare client vs. peer performance, such as transaction volumes.

Benchmarked metrics must comply with one of the approved rules below. Also, you must consider for each metric (1) whether the client or any recipient of the metric could discover or infer (i.e., “reverse engineer”) the identity or performance information about members of the benchmarked group, (2) whether the client could use the metric to facilitate anti-competitive effects (e.g., higher prices, reduced levels of service, coordination among competitors, etc.), and/or (3) the likelihood that third parties who are members of the benchmarked group will complain if the client were to successfully reverse engineer their identities or performance information.

The benchmarking rules do not need to be applied if a deliverable reflects only the issuer, acquirer, or merchant’s own data, i.e., if no peer group data is included.

**Special Citibank Rule**: When including Citibank in a peer group (i.e., when a Citi competitor is to receive the output), the peer group must meet one of the above rules, but Citi may only represent a maximum of 25% of the peer group even if 6/30, 7/35, or 10/40 are used.

**Fraud Metric Rules:** Fraud metrics should comply with benchmarking rules. When performing issuer benchmarking concentration checks (e.g., 5/25), use clearing spend for fraud and chargeback metrics.

<table>
<colgroup>
<col style="width: 24%" />
<col style="width: 75%" />
</colgroup>
<thead>
<tr>
<th><strong>Rule</strong></th>
<th style="text-align: left;"><strong>Description</strong></th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>5/25</strong></td>
<td style="text-align: left;"><p>Under the 5/25 rule, the peer group must consist of at least five participants. No participant’s information may be more than 25% of the metric being benchmarked.</p>
<p>For example, the following peer set is compliant: [25, 25, 25, 24, 1]</p></td>
</tr>
<tr>
<td><strong>6/30</strong></td>
<td style="text-align: left;"><p>Under the 6/30 rule, the peer group must consist of at least six participants. No one single participant’s information may be more than 30% and at least three participants’ information must be greater than or equal to 7%.</p>
<p>For example, the following peer sets are compliant: [30, 24.5, 24.5, 7, 7, 7] <strong>or</strong> [30, 30, 30, 3.33, 3.33, 3.33]</p></td>
</tr>
<tr>
<td><strong>7/35</strong></td>
<td style="text-align: left;"><p>Under the 7/35 rule, the peer group must consist of at least seven participants. No one single participant’s information may be more than 35%. At least two participants must be greater than or equal to 15%, and there must be at least one additional participant that is greater than or equal to 8%.</p>
<p>For example, the following peer sets are compliant: [35, 15, 15, 8.75, 8.75, 8.75, 8.75] <strong>or</strong> [35, 25, 25, 3.75, 3.75, 3.75, 3.75]</p></td>
</tr>
<tr>
<td><strong>10/40</strong></td>
<td style="text-align: left;"><p>Under the 10/40 rule, the peer group must consist of at least ten participants. No single participant's information may be more than 40%. At least two participants must be greater than or equal to 20% individually, and there must be at least one additional participant that is greater than or equal to 10%.</p>
<p>For example, the following two peer sets are compliant (even if they are unlikely in practice): [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6] <strong>or</strong> [40, 20, 10, 5, 5, 5, 5, 5, 4, 1]</p></td>
</tr>
<tr>
<td><strong>Merchant benchmarking only: 4/35</strong></td>
<td style="text-align: left;">For reports based on anonymized and aggregated merchant spend, it is permissible to apply an alternative rule where the peer group consists of at least four participants, and no single participant's information exceeds 35% of the metric being benchmarked.</td>
</tr>
</tbody>
</table>

For recurring deliverables, compliance with the above rules must be re-checked whenever the peer group is altered, and at least once per year even if the peer group is not altered to account for market share fluctuations.

## Examples of Compliant Benchmark Groups

### Merchant Benchmark Examples

In these examples, the client requesting benchmarked data is Merchant A (who is excluded from the peer set).  To determine the market shares of the peers, it is acceptable to use the Gross Dollar Volume (GDV) for the time period in which the benchmark is to be reported.

Example of data set complying with 5/25:

| **Merchant** | **GDV (\$)**     | **%**  |
|--------------|------------------|--------|
| Merchant A   | **\$33,000,000** | ** **  |
| Merchant B   | **\$22,000,000** | **22** |
| Merchant C   | **\$20,000,000** | **20** |
| Merchant D   | **\$18,000,000** | **18** |
| Merchant E   | **\$16,000,000** | **16** |
| Merchant F   | **\$14,000,000** | **14** |
| Merchant G   | **\$10,000,000** | **10** |
| **Total**    | \$100,000,000    | 100    |

Example of data set complying with 10/40:

| **Merchant** | **GDV (\$)**     | **%**  |
|--------------|------------------|--------|
| Merchant A   | **\$42,000,000** |        |
| Merchant B   | **\$38,000,000** | **38** |
| Merchant C   | **\$24,000,000** | **24** |
| Merchant D   | **\$16,000,000** | **16** |
| Merchant E   | **\$7,000,000**  | **7**  |
| Merchant F   | **\$5,000,000**  | **5**  |
| Merchant G   | **\$4,000,000**  | **4**  |
| Merchant H   | **\$2,000,000**  | **2**  |
| Merchant I   | **\$2,000,000**  | **2**  |
| Merchant J   | **\$1,000,000**  | **1**  |
| Merchant K   | **\$1,000,000**  | **1**  |
| **Total**    | \$100,000,000    | 100    |

### Issuer Benchmark Concentration Rule Examples

When providing benchmarked metrics to an issuer and Citibank is in the peer set, this is compliant:

| **Issuer** | %       |
|------------|---------|
| Issuer     |         |
| Bank A     | **12%** |
| Bank B     | **4%**  |
| Citibank   | **25%** |
| Bank D     | **32%** |
| Bank E     | **2%**  |
| Bank F     | **15%** |
| Bank G     | **10%** |
| **Total**  | 100%    |

## Potential Solutions for Non-Compliant Benchmark Groups

***Solution 1: Add more entities to the peer group**.*  This will dilute the market share of the dominant entity and may achieve compliance with the Benchmark Concentration Rule. For example:                   

If there are no other competitors to add to the peer group, consider expanding the definition of their peer group or region so that other entities may be included.  For example, consider expanding a “quick serve restaurant” peer group to include additional “casual dining restaurants”, or consider expanding a regional benchmark to include additional trade areas with new peers. *Provided there are initially at least five peers in the peer group, consider adding in the client’s share to whom the report will be delivered.*  Although the client share is typically excluded in first instance, it may help to dilute the market share of the dominant entity in the peer group.  See the example directly below.  Please note that if the client has a particularly large market share, this may not be a good solution because the peer group results may now be skewed toward the client’s own metrics.  Remember, the client can neither know which entities are in the peer group nor that itself has been included in the peer group. 

| **Issuer**     | **%**   |       | **Issuer**      | **%**  |
|----------------|---------|-------|-----------------|--------|
| Bank A         | ** 10** |       | Bank A          | **9**  |
| Bank B         | **40**  |       | Bank B          | **29** |
| Bank C         | **35**  | To    | Bank C          | **27** |
| Bank D         | **10**  |       | Bank D          | **9**  |
| Bank E         | **5**   | ** ** | Bank E          | **4**  |
|                | ** **   | ** ** | Client Bank X   | **22** |
| **Total**      | 100     |       | **Total**       | 100    |
| **Fails 5/25** |         |       | **Passes 6/30** |        |

*  
**Solution 2: Aggregate significant non-aggregate merchants**: *When benchmarking merchants, if the industry is one with significant non-aggregated (i.e., “mom-and-pop”, non-franchised) merchants, such as perhaps hair salons, at least five non-aggregated merchants may be combined to create an additional peer. In line with exception (d) below, another possibility is to expand the region or market to include additional peers from a nearby region or similar industry.  For example, if there are only four peers in an industry of quick serve restaurants, include a fast casual dining restaurant or a different quick serve restaurant from a nearby region.* *

***Solution 3: Where there are not enough entities to create a peer group of at least five, consider “borrowing” an entity who performs in a similar financial ecosystem so that the added peer will have metrics realistic to the client’s**.* For instance, see the example below.  However, note that for recurring reports, this solution may not be feasible, instead it may be better to expand the definition of the peer set as more fully described in exception (a) above.   

| **Issuer** | **%**  |     | **Issuer**        | **%**  |
|------------|--------|-----|-------------------|--------|
| Bank A     | **23** |     | Bank A            | **19** |
| Bank B     | **25** |     | Bank B            | **21** |
| Bank C     | **28** | to  | Bank C            | **24** |
| Bank D     | **24** |     | Bank D            | **20** |
|            | **87** |     | Bank E (borrowed) | **20** |
| **Total**  | 100    |     | **Total**         | 100    |

***Solution 4: Consider taking a straight or simple average instead of a weighted one when calculating metrics of a benchmark group***.  In this case, all of the entities in the peer set will have equal weighting and there will be no dominant peer. For example:

<table style="width:100%;">
<colgroup>
<col style="width: 13%" />
<col style="width: 28%" />
<col style="width: 0%" />
<col style="width: 0%" />
<col style="width: 9%" />
<col style="width: 0%" />
<col style="width: 25%" />
<col style="width: 19%" />
</colgroup>
<thead>
<tr>
<th colspan="2">Retail cobrand Benchmark</th>
<th></th>
<th></th>
<th></th>
<th></th>
<th></th>
<th></th>
</tr>
</thead>
<tbody>
<tr>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td></td>
<td colspan="2">Clearing $ Volume</td>
<td></td>
<td colspan="2">% of Total Spend</td>
<td>Number of Accounts</td>
<td>Average Spend/Account</td>
</tr>
<tr>
<td><u>Cobrand Merchant</u></td>
<td><u>FY 2015</u></td>
<td></td>
<td></td>
<td>FY 15</td>
<td></td>
<td></td>
<td>FY 15</td>
</tr>
<tr>
<td>Merchant A</td>
<td>          12,388,255,352</td>
<td></td>
<td></td>
<td>67.4%</td>
<td></td>
<td>        8,255,352</td>
<td>1501</td>
</tr>
<tr>
<td>Merchant B</td>
<td>               556,317,206</td>
<td></td>
<td></td>
<td>3.0%</td>
<td></td>
<td>                      46,587</td>
<td>11941</td>
</tr>
<tr>
<td>Merchant C</td>
<td>               815,327,016</td>
<td></td>
<td></td>
<td>4.4%</td>
<td></td>
<td>      15,327,016</td>
<td>53</td>
</tr>
<tr>
<td>Merchant D</td>
<td>            3,557,484,956</td>
<td></td>
<td></td>
<td>19.3%</td>
<td></td>
<td>      57,484,956</td>
<td>62</td>
</tr>
<tr>
<td>Merchant E</td>
<td>            1,070,145,275</td>
<td></td>
<td></td>
<td>5.8%</td>
<td></td>
<td>    170,145,275</td>
<td>6</td>
</tr>
<tr>
<td>Grand Total</td>
<td>          18,387,529,805</td>
<td></td>
<td></td>
<td>100%</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td colspan="7">Weighted Average: 1501 *(.674) + 11941*(.03) + 53*(.044)+62*(.193)+6*(.058) = 1011+358+2+12+0</td>
<td></td>
</tr>
<tr>
<td colspan="2">Weighted Average: = 1383/account</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td colspan="5">Straight Average:   = 1501+1941+53+62+6)/5=$2713/account</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
</tbody>
</table>

As seen in the illustration above, a weighted benchmark metric of this non-compliant peer set will provide metrics similar to the dominant entity’s actual metrics.  However, when a straight average is taken, the dominant entity’s share is diluted to protect its confidential performance information.

***Solution 5: Consider adjusting the volume of the dominant entity in the peer set**.  *For example:

| **PLATINUM** | **Sum of NCARDS** | **Sum of TXN** | ** ** | **7/35** | **Adjusted Cards** | **Adjusted TXN** | **Adjusted Amt** | **7/35** |
|----|----|----|----|----|----|----|----|----|
| Client Issuer X | 4,789 | 179,004 |  |  |  |  |  |  |
| Issuer A | 142 | 3,244 |  | 0.0% | 142 | 3,244 | 447,557 | 0.0% |
| Issuer B | 34,083 | 690,942 |  | 6.0% | 34,083 | 690,942 | 65,348,979 | 6.0% |
| Issuer C | 13,232 | 268,755 |  | 2.3% | 13,232 | 268,755 | 26,573,869 | 2.4% |
| Issuer D | 82,813 | 2,170,969 |  | 18.8% | 82,813 | 2,170,969 | 233,025,218 | 21.3% |
| Issuer E | 101,004 | 4,071,840 |  | 35.3% | 101,004 | 4,071,840 | 373,046,481 | 34.0% |
| Issuer F | 16,330 | 188,176 |  | 1.6% | 16,330 | 188,176 | 19,199,025 | 1.8% |
| Issuer G | 110,314 | 4,143,213 |  | 35.9% | 99,283 | 3,728,892 | 377,721,304 | 34.5% |
| Issuer H | 180 | 6,699 |  | 0.1% | 180 | 6,699 | 819,716 | 0.0% |
| **GRAND TOTAL** | 362,887 | 11,722,842 |  | 100.0% | 347,067 | 11,129,517 | 1,096,182,149 | 100.0% |

| **PLATINUM** | **cards** | **txn** | **amt** | **avg_txn** | **avg_spend** | **ticket** | **perc_amt_xb** |
|----|----|----|----|----|----|----|----|
| Client Issuer X | 4,789 | 179,004 | 19,777,626 | 37 | 4,130 | 110 | 17% |
| Benchmark | 347,067 | 11,129,517 | 1,096,362,149 | 32 | 3,159 | 99 | 20% |

In the above example, because the peer group did not meet the Benchmark Concentration Rule, several portfolios of the dominant peer were removed which reduced the volume and subsequent market share of that dominant peer in order to create a benchmark compliant peer group.

In this example below, the GDV was adjusted slightly to create the now benchmark compliant peer group.

| **Issuer**     | **GDV**    | **%**  |     | **Issuer**     | **GDV**    | **%**  |     |     |     |
|----------------|------------|--------|-----|----------------|------------|--------|-----|-----|-----|
| Bank A         | 108559     | **37** |     | Bank A         | 102787     | **35** |     |     |     |
| Bank B         | 83746      | **28** |     | Bank B         | 83746      | **29** |     |     |     |
| Bank C         | 40345      | **14** | to  | Bank C         | 40345      | **14** |     |     |     |
| Bank D         | 20192      | **7**  |     | Bank D         | 20192      | **7**  |     |     |     |
| Bank E         | 21704      | **7**  |     | Bank E         | 21704      | **7**  |     |     |     |
| Bank F         | 16972      | **6**  |     | Bank F         | 16972      | **6**  |     |     |     |
| Bank G         | 3838       | **1**  |     | Bank G         | 3838       | **1**  |     |     |     |
| **Total**      | **295356** | 100    |     | **Total**      | **289584** | 100    |     |     |     |
| **Fails 7/35** |            |        |     | **Meets 7/35** |            |        |     |     |     |

***Solution 6: Consider providing a simple data point with no specific metrics where there are only 2 or 3 entities in a market and an expanded market is not desirable**. *In the case where there are so few competitors in a region, a single “data point” may be provided in a statement to provide directional guidance to a client.  For instance, alongside an issuer client’s own metrics on its market share in several MCCs, could be a directional statement such as “client is overperforming the grocery, women’s apparel and toy store industries, yet underperforming in accommodations and airlines MCCs.”  This will provide guidance to the client while at the same time protecting the confidential performance information of its few competitors.

| **Issuer** | **%**  | ** ** | **Issuer** | **%**  |
|------------|--------|-------|------------|--------|
| Bank A     | **75** | ** ** | Bank A     | **56** |
| Bank B     | **25** | or    | Bank B     | **23** |
| **Total**  | 100    |       | Bank C     | **21** |
| ** **      |        |       | **Total**  | 100    |

## Handling Issuer Requests for Top Merchants

When multiple types of entities are involved (for example, in an issuer's request for a benchmark of top merchants), it is important to ensure that the confidential performance information of all the relevant players is properly protected. For example (as illustrated below), an issuer may ask for the "top ten merchants that its cardholders transacted with" and benchmark metrics for a peer set of other issuers. In order to protect the confidential performance information of the peer set issuers and the top merchants, the benchmark metrics **cannot** disclose the top ten merchants for each of the peer set issuers. Instead, the benchmark metric for each top merchant must be based on the peer set's performance in the corresponding MCC. Therefore, in the example below, the benchmark metric for Merchant 1 (a grocery store) must show the peer set's percentage of total transactions in the grocery MCC as a whole (**not** at Merchant 1 only). In order for this metric to protect the confidential performance information of the peer set issuers **AND** the merchants, we must ensure (1) that the issuers included in the peer set meet the minimum number and maximum concentration for spend within the grocery MCC to be benchmark compliant, **AND** (2) that the merchants included in the grocery MCC meet the requisite number and concentration to be benchmark compliant (e.g., if there are only 5 merchants in the grocery MCC, then Merchant 1 may not account for more than 25% of spend in the MCC). This is also the case when providing benchmarked metrics to merchants, or when benchmarking contactless payments for issuers (as discussed above).  In all scenarios, be sure the confidential performance information of all relevant entities is protected.

<table>
<colgroup>
<col style="width: 34%" />
<col style="width: 32%" />
<col style="width: 32%" />
</colgroup>
<thead>
<tr>
<th><strong>Client Issuer's Top Merchants</strong></th>
<th style="text-align: left;"><p><strong>% of Total Transactions by</strong></p>
<p><strong>Client Issuer's Cardholders</strong></p></th>
<th style="text-align: left;"><p><strong>% of Total Transactions at</strong></p>
<p><strong>Corresponding MCC</strong></p>
<p><strong>for Issuer Peer Set</strong></p></th>
</tr>
</thead>
<tbody>
<tr>
<td>Merchant 1: Grocery A</td>
<td>6.56%</td>
<td>Grocery MCC:  4.21%</td>
</tr>
<tr>
<td>Merchant 2: Hotel A</td>
<td>6.00%</td>
<td>Hotel MCC:  5.21%</td>
</tr>
<tr>
<td>Merchant 3: Airline A</td>
<td>3.06%</td>
<td> Airline MCC*:  3.45%</td>
</tr>
<tr>
<td>Merchant 4: Hotel B</td>
<td>3.00%</td>
<td>Hotel MCC:  5.21%</td>
</tr>
<tr>
<td>Merchant 5: Apparel A</td>
<td>2.54%</td>
<td>Apparel MCC:  4.23%</td>
</tr>
<tr>
<td>Merchant 6: Hotel C</td>
<td>2.30%</td>
<td>Hotel MCC:  5.21%</td>
</tr>
<tr>
<td>Merchant 7: Petrol A</td>
<td>2.02%</td>
<td>Petrol MCC: 1.10%</td>
</tr>
<tr>
<td>Merchant 8: Jewelry A</td>
<td>1.87%</td>
<td>Jewelry MCC: 3.00%</td>
</tr>
<tr>
<td>Merchant 9: Grocery B</td>
<td>1.63%</td>
<td>Grocery MCC 4.21%</td>
</tr>
<tr>
<td>Merchant 10: Petrol B</td>
<td>1.53%</td>
<td>Petrol MCC 1.10%</td>
</tr>
<tr>
<td><strong>Top 10 as a % of total</strong></td>
<td>30.50%</td>
<td></td>
</tr>
</tbody>
</table>

\*There are some categories of MCCs (such as airlines) where each merchant may have its own MCC.  In these cases, the individual MCCs (e.g., the airlines) must be aggregated together in order to comply with benchmarking guidelines.

## Malls and Retail Parks

When conducting benchmarking for a retail park, special benchmarking guidelines must be met.  A retail park may be defined as (i) a large retail setting such as a single building with a variety of merchants; (ii) an open air or “strip” retail park; (iii) outlet stores grouped together; or (iv) stores on land owned by a common owner.  Importantly, the owner of a retail park is **<u>not</u>** a merchant; therefore, the retail park owner cannot receive confidential performance metrics about individual merchants in its retail park without merchant consent.  However, Mastercard can provide limited benchmarked insights so a retail park owner can understand how its retail park is performing.  The rules discussed here apply to reports provided to retail park owners. 

**Providing insights about a retail park**

While each individual merchant in a retail park may have access to their own insights about their individual store performance, the retail park owner may receive metrics about the aggregated merchants in its retail park provided that:

(i) The Benchmark Concentration Rule is met so that no single merchant in the benchmark group of retail park stores makes up more than 25% of the **transactions** in the benchmark group; and

\(ii\) No single merchant in the benchmark group of retail park stores makes up more than 25% of the **GDV** in the benchmark group; and

\(iii\) The report must be based on “aged” data.

In addition, a retail park owner may receive insights at the MCC level to understand how retail categories are performing within its retail park (e.g., restaurants, beauty supplies, women’s apparel, department stores), provided that: the Benchmark Concentration Rule is met; and the report is based on “aged” data. 

- In the example facility above, the retail park owner may be provided information about spend and transactions in each category with more than five stores.

- The retail park owner would not be allowed to get insights about any individual store without that merchant’s consent.

<!-- -->

- In the example above, the retail park owner may receive insights related to the merchant categories in the retail park.

- No merchant in a mall may be more than 25% of volume or transactions in reports on the retail park.

**Providing comparative insights to other retail parks**

A retail park may receive insights to understand how it is performance against other retail parks or shopping areas. However, individual retail park to retail park comparisons are not allowable, as it is important not to disclose the confidential performance information of one retail park to another.  To provide such comparative performance metrics, insights can be provided if:

\(i\) The retail park (group of merchants in a benchmark compliant peer group as per Section (a) above is met; and

\(ii\) The retail park is compared to:

1.   a peer group of at least five other retail parks is a benchmark compliant peer group; or

2.  A city (e.g., a retail park compared to aggregated benchmark compliant peer group of New York City stores) whereby the report may assess the contribution of, for example, New York City postal codes to sales in the retail park and compare this to New York City sales; or

3.  A trade area, such as a benchmark compliant peer group of stores within a particular distance from the retail park.  Note that when providing this comparison, the trade area size must not be disclosed to the retail owner so that they cannot infer the stores included.  When creating a trade area peer group, there must be at least five merchants in at least five different MCCs, each being benchmark compliant. 

- The example above illustrates that a direct mall-to-mall comparison is not allowed.

- The above example depicts a mall to city comparison, or a mall to a group of malls comparison.

## Sample Q&A with Clients

You may receive questions about benchmarking from clients or prospects. To help you respond to questions, here are some frequently asked questions and suggested responses.

**What are Mastercard’s benchmarking rules?**

Mastercard has restrictions in place to control the share that any one entity may have in a peer group. These are designed to protect the confidential performance information of individual entities and comply with best practices around information sharing.  

**Why does Mastercard apply these rules?**

The rules help ensure that statistics for a peer set are not simply a reflection of one dominant player, rather, the insights reflect a more balanced market share of all participating entities.

**Who is in my peer set?**

Mastercard does not disclose the identities of peer sets in order to preserve the confidentiality of peer information. Similarly, we would never disclose to a competitor of yours that your entity’s information was included in their benchmark peer set.

**Can I choose who should be in my peer set?**

You can inform us of your preferred entities or type of entities to be included in the peer set and Mastercard will take into consideration your suggestions. However, in order to preserve the confidentiality of peer information, Mastercard will not confirm whether and which of those entities are included in the peer set (if any).

## Best in Class Metrics

A “Best in Class” metric may be provided for a peer group so long as the Best in Class entity is selected independent of any other metric provided.  That is, a single entity may not be selected as Best in Class for all periods and measures unless it is independently selected as such for each period and measure. To note, the meaning of Best in Class may vary depending on the metric (i.e., highest approval rate vs. lowest decline rate).  To calculate Best in Class for each metric for a peer group, rank the resulting metrics in order, ignore missing values and weighted averages, and Best in Class is the 85% percentile (the value for which 85% of the group did worse than and 15% did better for the peer set. As seen in the example below :

<img src="docs\control-3-media/media/image1.png" style="width:5.90069in;height:1.23365in" />

The Best in Class is 24.7 (highest rank)\*- (.15)\*16 entities = 22.3%.  Note, that this number does <u>not</u> correlate to any actual value, rather it provides an accurate Best in Class view of market performance across the peer group while ensuring the privacy of each entity’s confidential performance data.

# Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client

If a deliverable includes metrics that benchmark a client’s performance versus its peers or a category:

- Mastercard must independently select the members of the peer group, and may not disclose the identities of the members of the peer group to the client, even if it masks the peers’ actual identities (e.g., replaces “Company X” with “P1”).

- For **financial or transactional metrics**, Mastercard may not disclose performance metrics on a per-peer basis. Mastercard may only report (1) the client’s metric and (2) average of the peer group’s metrics.

- For **operational metrics** (e.g., fraud, authorization, acceptance, or chargeback rates reported as growth rates or indices), Mastercard may report, **using indices only**, (1) the client’s metric and (2) each peer’s metric, if peer names are removed.

A client may provide Mastercard with a description of the types of entities the client would prefer in a peer group. For example, a high-end hotel may wish to be compared to only luxury hotels rather than budget motels or hostels, and may name specific merchants for comparison. In that case, some (but not all) of the peer group may be made up of the client’s suggested entities, so long as the client does not know which or how many.

# Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review 

We treat mobile payment or digital wallet providers like Apple and Google, and transactions that take place through digital wallets, differently from other clients and transactions because those providers are not a financial institutions or merchants, and our Rules do not give them the right to see transactions that occurred though their technology. Additionally, our agreements with certain providers may contractually limit the types of metrics we may report to them or about them.

**Do not** disclose metrics about a mobile payment or digital wallet provider’s performance to an issuer, acquirer, or merchant, without obtaining Privacy review.

**Do not** disclose metrics about an issuer, acquirer, or merchant’s performance to a mobile payment or digital wallet provider, without obtaining Privacy review.

These limitations mean that Mastercard cannot provide a digital wallet provider with benchmark metrics comparing issuer, acquirer, or merchant performance with a benchmarked group of digital wallets.

If you need to deliver metrics related to digital wallets, consider these alternatives:

- Reframing the metric so that it includes all contactless payments.

- Creating a deliverable that describes the impact digital wallet engagement has had on payment card usage, e.g., a “lift analysis” showing growth rates in cardholder engagement before and after digital wallet adoption, or a comparison showing consumer spend insights for consumers who adopted digital wallets versus similar consumers who did not.
