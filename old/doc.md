Control 3 - Customer/Merchant Performance

Services Privacy

Exported on 2025-10-28 12:15:13

Table of Contents

1 Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another 4

2 Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds 5

2.1 Examples of Compliant Benchmark Groups 6

2.1.1 Merchant Benchmark Examples 6

2.1.2 Issuer Benchmark Concentration Rule Examples 7

2.2 Potential Solutions for Non-Compliant Benchmark Groups 7

2.3 Handling Issuer Requests for Top Merchants 11

2.4 Malls and Retail Parks 12

2.5 Sample Q&A with Clients 13

2.6 Best in Class Metrics 13

3 Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client 15

4 Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review 16

**CONFIDENTIAL / NOT FOR EXTERNAL DISTRIBUTION**

* [Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another](#scroll-bookmark-3)
* [Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds](#scroll-bookmark-4)
  + [Examples of Compliant Benchmark Groups](#scroll-bookmark-5)
    - [Merchant Benchmark Examples](#scroll-bookmark-6)
    - [Issuer Benchmark Concentration Rule Examples](#scroll-bookmark-7)
  + [Potential Solutions for Non-Compliant Benchmark Groups](#scroll-bookmark-8)
  + [Handling Issuer Requests for Top Merchants](#scroll-bookmark-9)
  + [Malls and Retail Parks](#scroll-bookmark-10)
  + [Sample Q&A with Clients](#scroll-bookmark-11)
  + [Best in Class Metrics](#scroll-bookmark-12)
* [Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client](#scroll-bookmark-13)
* [Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review](#scroll-bookmark-14)

The controls below are intended to protect the confidentiality of client and merchant performance data by, for example, applying benchmarking rules, preserving the confidentiality/composition of peer groups, and adhering to contractual obligations.

Please note that information exchange and competition laws are an evolving area. The controls below, by themselves, may not always be sufficient to protect against anti-competitive activity. In some circumstances, it may be necessary for product teams to work with competition law counsel, Data Strategy, and Privacy to apply additional or alternative controls where appropriate.

For questions, please create an [Intake Brief](https://confluence.mastercard.int/pages/viewpage.action?pageId=849582763) and contact the member of the Privacy team responsible for your region.

**Critical Notes**

* **You may not report digital wallet metrics without Privacy approval. See Control 3.4.**
* **You may not create a deliverable that includes a list of “top merchants,” even if you mask the identity of individual merchants.**
* **Market share analyses (e.g., an analysis of an entire geographic region, country, MCC, or industry) are a type of benchmark analysis that can be sensitive from a competition and investor relations perspective. Market share metrics must comply with Controls 3 and 4.**
* **When including Citibank in a peer group (i.e., when a Citi competitor is to receive the output), the peer group must meet one of the above rules, but Citi may only represent a maximum of 25% of the peer group even if 6/30, 7/35, or 10/40 are used.**

# Control 3.1: Mastercard May Not Disclose Information about the Performance of One Entity to Another

Mastercard’s transaction data can be used to assess the performance of a variety of stakeholders in the payments ecosystem. In many cases, clients want insights into their own performance as well as the performance of their competitors, partners, subsidiaries, or other third parties. Mastercard cannot provide insights that are indicative of one entity’s performance to another entity unless the entity or entities whose performance is being disclosed provide their permission and the information sharing would not otherwise lead to anti-competitive effects (e.g., higher prices, reduced levels of service, coordination among competitors, etc.). If you have any doubts about whether the information sharing may lead to anti-competitive activity, please consult the Privacy or legal teams.

Use cases that **require** legal review include where we provide or create:

* An issuer’s co-brand portfolio metrics to the co-brand partner. Note: Delivering co-brand metrics to the co-brand merchant requires Mastercard to obtain a consent letter from the co-brand card issuer. This is because the disclosure of co-brand metrics to the merchant represents the confidential performance information of the co-brand issuer.
* Spend metrics about merchants in a mall to the mall owner.
* Metrics to a publisher that measure the performance of specific merchant campaigns run on the publisher’s platform. A “publisher” is any entity that displays advertisements on its properties, e.g., a website owner or a sports stadium.
* An issuer’s portfolio spend metrics to a payment processor or program manager.
* Metrics about an entity’s performance to a potential buyer or its representatives in an M&A context.
* Metrics or a score about an entity, using transaction data pertaining to that entity, for evaluation purposes (e.g., to support lending decisions, invoicing or debt collection, etc.).
* A deliverable for a franchisor about a franchisee, or vice versa.
* Metrics to an aggregator or intermediary that resells our metrics to its client or combines our metrics with third-party data.

# Control 3.2: Benchmarked Analytics Must Meet Certain Thresholds

If a client deliverable includes metrics that describe the performance of a group of third parties (i.e., entities that are not the client itself), Mastercard must obfuscate the performance of individual entities contained in those group metrics in a way that limits the client’s ability to discover or infer the identity or performance information of any individual entity in the group. Benchmarked analytics include:

* Market share analyses.
* Analyses of the performance of an MCC, industry, product type, geography, market, segment, or other category that includes transaction data of multiple issuers, acquirers, or merchants.
* Benchmarks that compare client vs. peer performance, such as transaction volumes.

Benchmarked metrics must comply with one of the approved rules below. Also, you must consider for each metric (1) whether the client or any recipient of the metric could discover or infer (i.e., “reverse engineer”) the identity or performance information about members of the benchmarked group, (2) whether the client could use the metric to facilitate anti-competitive effects (e.g., higher prices, reduced levels of service, coordination among competitors, etc.), and/or (3) the likelihood that third parties who are members of the benchmarked group will complain if the client were to successfully reverse engineer their identities or performance information.

The benchmarking rules do not need to be applied if a deliverable reflects only the issuer, acquirer, or merchant’s own data, i.e., if no peer group data is included.

**Special Citibank Rule**: When including Citibank in a peer group (i.e., when a Citi competitor is to receive the output), the peer group must meet one of the above rules, but Citi may only represent a maximum of 25% of the peer group even if 6/30, 7/35, or 10/40 are used.

**Fraud Metric Rules:** Fraud metrics should comply with benchmarking rules. When performing issuer benchmarking concentration checks (e.g., 5/25), use clearing spend for fraud and chargeback metrics.

|  |  |
| --- | --- |
| **Rule** | **Description** |
| **5/25** | Under the 5/25 rule, the peer group must consist of at least five participants. No participant’s information may be more than 25% of the metric being benchmarked.  For example, the following peer set is compliant: [25, 25, 25, 24, 1] |
| **6/30** | Under the 6/30 rule, the peer group must consist of at least six participants. No one single participant’s information may be more than 30% and at least three participants’ information must be greater than or equal to 7%.  For example, the following peer sets are compliant: [30, 24.5, 24.5, 7, 7, 7] **or** [30, 30, 30, 3.33, 3.33, 3.33] |
| **7/35** | Under the 7/35 rule, the peer group must consist of at least seven participants. No one single participant’s information may be more than 35%. At least two participants must be greater than or equal to 15%, and there must be at least one additional participant that is greater than or equal to 8%.  For example, the following peer sets are compliant: [35, 15, 15, 8.75, 8.75, 8.75, 8.75] **or** [35, 25, 25, 3.75, 3.75, 3.75, 3.75] |
| **10/40** | Under the 10/40 rule, the peer group must consist of at least ten participants. No single participant's information may be more than 40%. At least two participants must be greater than or equal to 20% individually, and there must be at least one additional participant that is greater than or equal to 10%.  For example, the following two peer sets are compliant (even if they are unlikely in practice): [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6] **or** [40, 20, 10, 5, 5, 5, 5, 5, 4, 1] |
| **Merchant benchmarking only: 4/35** | For reports based on anonymized and aggregated merchant spend, it is permissible to apply an alternative rule where the peer group consists of at least four participants, and no single participant's information exceeds 35% of the metric being benchmarked. |

For recurring deliverables, compliance with the above rules must be re-checked whenever the peer group is altered, and at least once per year even if the peer group is not altered to account for market share fluctuations.

## Examples of Compliant Benchmark Groups

### Merchant Benchmark Examples

In these examples, the client requesting benchmarked data is Merchant A (who is excluded from the peer set).  To determine the market shares of the peers, it is acceptable to use the Gross Dollar Volume (GDV) for the time period in which the benchmark is to be reported.

Example of data set complying with 5/25:

|  |  |  |
| --- | --- | --- |
| **Merchant** | **GDV ($)** | **%** |
| Merchant A | **$33,000,000** |  |
| Merchant B | **$22,000,000** | **22** |
| Merchant C | **$20,000,000** | **20** |
| Merchant D | **$18,000,000** | **18** |
| Merchant E | **$16,000,000** | **16** |
| Merchant F | **$14,000,000** | **14** |
| Merchant G | **$10,000,000** | **10** |
| **Total** | $100,000,000 | 100 |

Example of data set complying with 10/40:

|  |  |  |
| --- | --- | --- |
| **Merchant** | **GDV ($)** | **%** |
| Merchant A | **$42,000,000** |  |
| Merchant B | **$38,000,000** | **38** |
| Merchant C | **$24,000,000** | **24** |
| Merchant D | **$16,000,000** | **16** |
| Merchant E | **$7,000,000** | **7** |
| Merchant F | **$5,000,000** | **5** |
| Merchant G | **$4,000,000** | **4** |
| Merchant H | **$2,000,000** | **2** |
| Merchant I | **$2,000,000** | **2** |
| Merchant J | **$1,000,000** | **1** |
| Merchant K | **$1,000,000** | **1** |
| **Total** | $100,000,000 | 100 |

### Issuer Benchmark Concentration Rule Examples

When providing benchmarked metrics to an issuer and Citibank is in the peer set, this is compliant:

|  |  |
| --- | --- |
| **Issuer** | % |
| Issuer |  |
| Bank A | **12%** |
| Bank B | **4%** |
| Citibank | **25%** |
| Bank D | **32%** |
| Bank E | **2%** |
| Bank F | **15%** |
| Bank G | **10%** |
| **Total** | 100% |

## Potential Solutions for Non-Compliant Benchmark Groups

***Solution 1: Add more entities to the peer group****.*  This will dilute the market share of the dominant entity and may achieve compliance with the Benchmark Concentration Rule. For example:

If there are no other competitors to add to the peer group, consider expanding the definition of their peer group or region so that other entities may be included.  For example, consider expanding a “quick serve restaurant” peer group to include additional “casual dining restaurants”, or consider expanding a regional benchmark to include additional trade areas with new peers. *Provided there are initially at least five peers in the peer group, consider adding in the client’s share to whom the report will be delivered.*  Although the client share is typically excluded in first instance, it may help to dilute the market share of the dominant entity in the peer group.  See the example directly below.  Please note that if the client has a particularly large market share, this may not be a good solution because the peer group results may now be skewed toward the client’s own metrics.  Remember, the client can neither know which entities are in the peer group nor that itself has been included in the peer group.

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **Issuer** | **%** |  | **Issuer** | **%** |
| Bank A | **10** |  | Bank A | **9** |
| Bank B | **40** |  | Bank B | **29** |
| Bank C | **35** | To | Bank C | **27** |
| Bank D | **10** |  | Bank D | **9** |
| Bank E | **5** |  | Bank E | **4** |
|  |  |  | Client Bank X | **22** |
| **Total** | 100 |  | **Total** | 100 |
| **Fails 5/25** |  |  | **Passes 6/30** |  |

***Solution 2: Aggregate significant non-aggregate merchants****:*When benchmarking merchants, if the industry is one with significant non-aggregated (i.e., “mom-and-pop”, non-franchised) merchants, such as perhaps hair salons, at least five non-aggregated merchants may be combined to create an additional peer. In line with exception (d) below, another possibility is to expand the region or market to include additional peers from a nearby region or similar industry.  For example, if there are only four peers in an industry of quick serve restaurants, include a fast casual dining restaurant or a different quick serve restaurant from a nearby region.

***Solution 3: Where there are not enough entities to create a peer group of at least five, consider “borrowing” an entity who performs in a similar financial ecosystem so that the added peer will have metrics realistic to the client’s****.* For instance, see the example below.  However, note that for recurring reports, this solution may not be feasible, instead it may be better to expand the definition of the peer set as more fully described in exception (a) above.

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **Issuer** | **%** |  | **Issuer** | **%** |
| Bank A | **23** |  | Bank A | **19** |
| Bank B | **25** |  | Bank B | **21** |
| Bank C | **28** | to | Bank C | **24** |
| Bank D | **24** |  | Bank D | **20** |
|  | **87** |  | Bank E (borrowed) | **20** |
| **Total** | 100 |  | **Total** | 100 |

***Solution 4: Consider taking a straight or simple average instead of a weighted one when calculating metrics of a benchmark group***.  In this case, all of the entities in the peer set will have equal weighting and there will be no dominant peer. For example:

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Retail cobrand Benchmark | |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |
|  | Clearing $ Volume | |  | % of Total Spend | | Number of Accounts | Average Spend/Account |
| Cobrand Merchant | FY 2015 |  |  | FY 15 |  |  | FY 15 |
| Merchant A | 12,388,255,352 |  |  | 67.4% |  | 8,255,352 | 1501 |
| Merchant B | 556,317,206 |  |  | 3.0% |  | 46,587 | 11941 |
| Merchant C | 815,327,016 |  |  | 4.4% |  | 15,327,016 | 53 |
| Merchant D | 3,557,484,956 |  |  | 19.3% |  | 57,484,956 | 62 |
| Merchant E | 1,070,145,275 |  |  | 5.8% |  | 170,145,275 | 6 |
| Grand Total | 18,387,529,805 |  |  | 100% |  |  |  |
|  |  |  |  |  |  |  |  |
| Weighted Average: 1501 \*(.674) + 11941\*(.03) + 53\*(.044)+62\*(.193)+6\*(.058) = 1011+358+2+12+0 | | | | | | |  |
| Weighted Average: = 1383/account | |  |  |  |  |  |  |
| Straight Average:   = 1501+1941+53+62+6)/5=$2713/account | | | | |  |  |  |
|  |  |  |  |  |  |  |  |

As seen in the illustration above, a weighted benchmark metric of this non-compliant peer set will provide metrics similar to the dominant entity’s actual metrics.  However, when a straight average is taken, the dominant entity’s share is diluted to protect its confidential performance information.

***Solution 5: Consider adjusting the volume of the dominant entity in the peer set****.*For example:

|  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **PLATINUM** | **Sum of NCARDS** | **Sum of TXN** |  | **7/35** | **Adjusted Cards** | **Adjusted TXN** | **Adjusted Amt** | **7/35** |
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

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **PLATINUM** | **cards** | **txn** | **amt** | **avg\_txn** | **avg\_spend** | **ticket** | **perc\_amt\_xb** |
| Client Issuer X | 4,789 | 179,004 | 19,777,626 | 37 | 4,130 | 110 | 17% |
| Benchmark | 347,067 | 11,129,517 | 1,096,362,149 | 32 | 3,159 | 99 | 20% |

In the above example, because the peer group did not meet the Benchmark Concentration Rule, several portfolios of the dominant peer were removed which reduced the volume and subsequent market share of that dominant peer in order to create a benchmark compliant peer group.

In this example below, the GDV was adjusted slightly to create the now benchmark compliant peer group.

|  |  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Issuer** | **GDV** | **%** |  | **Issuer** | **GDV** | **%** |  |  |  |
| Bank A | 108559 | **37** |  | Bank A | 102787 | **35** |  |  |  |
| Bank B | 83746 | **28** |  | Bank B | 83746 | **29** |  |  |  |
| Bank C | 40345 | **14** | to | Bank C | 40345 | **14** |  |  |  |
| Bank D | 20192 | **7** |  | Bank D | 20192 | **7** |  |  |  |
| Bank E | 21704 | **7** |  | Bank E | 21704 | **7** |  |  |  |
| Bank F | 16972 | **6** |  | Bank F | 16972 | **6** |  |  |  |
| Bank G | 3838 | **1** |  | Bank G | 3838 | **1** |  |  |  |
| **Total** | **295356** | 100 |  | **Total** | **289584** | 100 |  |  |  |
| **Fails 7/35** |  |  |  | **Meets 7/35** |  |  |  |  |  |

***Solution 6: Consider providing a simple data point with no specific metrics where there are only 2 or 3 entities in a market and an expanded market is not desirable****.*In the case where there are so few competitors in a region, a single “data point” may be provided in a statement to provide directional guidance to a client.  For instance, alongside an issuer client’s own metrics on its market share in several MCCs, could be a directional statement such as “client is overperforming the grocery, women’s apparel and toy store industries, yet underperforming in accommodations and airlines MCCs.”  This will provide guidance to the client while at the same time protecting the confidential performance information of its few competitors.

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **Issuer** | **%** |  | **Issuer** | **%** |
| Bank A | **75** |  | Bank A | **56** |
| Bank B | **25** | or | Bank B | **23** |
| **Total** | 100 |  | Bank C | **21** |
|  |  |  | **Total** | 100 |

## Handling Issuer Requests for Top Merchants

When multiple types of entities are involved (for example, in an issuer's request for a benchmark of top merchants), it is important to ensure that the confidential performance information of all the relevant players is properly protected. For example (as illustrated below), an issuer may ask for the "top ten merchants that its cardholders transacted with" and benchmark metrics for a peer set of other issuers. In order to protect the confidential performance information of the peer set issuers and the top merchants, the benchmark metrics **cannot** disclose the top ten merchants for each of the peer set issuers. Instead, the benchmark metric for each top merchant must be based on the peer set's performance in the corresponding MCC. Therefore, in the example below, the benchmark metric for Merchant 1 (a grocery store) must show the peer set's percentage of total transactions in the grocery MCC as a whole (**not** at Merchant 1 only). In order for this metric to protect the confidential performance information of the peer set issuers **AND** the merchants, we must ensure (1) that the issuers included in the peer set meet the minimum number and maximum concentration for spend within the grocery MCC to be benchmark compliant, **AND** (2) that the merchants included in the grocery MCC meet the requisite number and concentration to be benchmark compliant (e.g., if there are only 5 merchants in the grocery MCC, then Merchant 1 may not account for more than 25% of spend in the MCC). This is also the case when providing benchmarked metrics to merchants, or when benchmarking contactless payments for issuers (as discussed above).  In all scenarios, be sure the confidential performance information of all relevant entities is protected.

|  |  |  |
| --- | --- | --- |
| **Client Issuer's Top Merchants** | **% of Total Transactions by**  **Client Issuer's Cardholders** | **% of Total Transactions at**  **Corresponding MCC**  **for Issuer Peer Set** |
| Merchant 1: Grocery A | 6.56% | Grocery MCC:  4.21% |
| Merchant 2: Hotel A | 6.00% | Hotel MCC:  5.21% |
| Merchant 3: Airline A | 3.06% | Airline MCC\*:  3.45% |
| Merchant 4: Hotel B | 3.00% | Hotel MCC:  5.21% |
| Merchant 5: Apparel A | 2.54% | Apparel MCC:  4.23% |
| Merchant 6: Hotel C | 2.30% | Hotel MCC:  5.21% |
| Merchant 7: Petrol A | 2.02% | Petrol MCC: 1.10% |
| Merchant 8: Jewelry A | 1.87% | Jewelry MCC: 3.00% |
| Merchant 9: Grocery B | 1.63% | Grocery MCC 4.21% |
| Merchant 10: Petrol B | 1.53% | Petrol MCC 1.10% |
| **Top 10 as a % of total** | 30.50% |  |

\*There are some categories of MCCs (such as airlines) where each merchant may have its own MCC.  In these cases, the individual MCCs (e.g., the airlines) must be aggregated together in order to comply with benchmarking guidelines.

## Malls and Retail Parks

When conducting benchmarking for a retail park, special benchmarking guidelines must be met.  A retail park may be defined as (i) a large retail setting such as a single building with a variety of merchants; (ii) an open air or “strip” retail park; (iii) outlet stores grouped together; or (iv) stores on land owned by a common owner.  Importantly, the owner of a retail park is **not** a merchant; therefore, the retail park owner cannot receive confidential performance metrics about individual merchants in its retail park without merchant consent.  However, Mastercard can provide limited benchmarked insights so a retail park owner can understand how its retail park is performing.  The rules discussed here apply to reports provided to retail park owners.

**Providing insights about a retail park**

While each individual merchant in a retail park may have access to their own insights about their individual store performance, the retail park owner may receive metrics about the aggregated merchants in its retail park provided that:

(i) The Benchmark Concentration Rule is met so that no single merchant in the benchmark group of retail park stores makes up more than 25% of the **transactions** in the benchmark group; and

(ii) No single merchant in the benchmark group of retail park stores makes up more than 25% of the **GDV** in the benchmark group; and

(iii) The report must be based on “aged” data.

In addition, a retail park owner may receive insights at the MCC level to understand how retail categories are performing within its retail park (e.g., restaurants, beauty supplies, women’s apparel, department stores), provided that: the Benchmark Concentration Rule is met; and the report is based on “aged” data.

* In the example facility above, the retail park owner may be provided information about spend and transactions in each category with more than five stores.
* The retail park owner would not be allowed to get insights about any individual store without that merchant’s consent.
* In the example above, the retail park owner may receive insights related to the merchant categories in the retail park.
* No merchant in a mall may be more than 25% of volume or transactions in reports on the retail park.

**Providing comparative insights to other retail parks**

A retail park may receive insights to understand how it is performance against other retail parks or shopping areas. However, individual retail park to retail park comparisons are not allowable, as it is important not to disclose the confidential performance information of one retail park to another.  To provide such comparative performance metrics, insights can be provided if:

(i) The retail park (group of merchants in a benchmark compliant peer group as per Section (a) above is met; and

(ii) The retail park is compared to:

1. a peer group of at least five other retail parks is a benchmark compliant peer group; or
2. A city (e.g., a retail park compared to aggregated benchmark compliant peer group of New York City stores) whereby the report may assess the contribution of, for example, New York City postal codes to sales in the retail park and compare this to New York City sales; or
3. A trade area, such as a benchmark compliant peer group of stores within a particular distance from the retail park.  Note that when providing this comparison, the trade area size must not be disclosed to the retail owner so that they cannot infer the stores included.  When creating a trade area peer group, there must be at least five merchants in at least five different MCCs, each being benchmark compliant.

* The example above illustrates that a direct mall-to-mall comparison is not allowed.
* The above example depicts a mall to city comparison, or a mall to a group of malls comparison.

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

![](data:image/png;base64...)

The Best in Class is 24.7 (highest rank)\*- (.15)\*16 entities = 22.3%.  Note, that this number does not correlate to any actual value, rather it provides an accurate Best in Class view of market performance across the peer group while ensuring the privacy of each entity’s confidential performance data.

# Control 3.3: Mastercard May Not Disclose Any Information about the Composition of a Peer Group or Category to a Client

If a deliverable includes metrics that benchmark a client’s performance versus its peers or a category:

* Mastercard must independently select the members of the peer group, and may not disclose the identities of the members of the peer group to the client, even if it masks the peers’ actual identities (e.g., replaces “Company X” with “P1”).
* For **financial or transactional metrics**, Mastercard may not disclose performance metrics on a per-peer basis. Mastercard may only report (1) the client’s metric and (2) average of the peer group’s metrics.
* For **operational metrics** (e.g., fraud, authorization, acceptance, or chargeback rates reported as growth rates or indices), Mastercard may report, **using indices only**, (1) the client’s metric and (2) each peer’s metric, if peer names are removed.

A client may provide Mastercard with a description of the types of entities the client would prefer in a peer group. For example, a high-end hotel may wish to be compared to only luxury hotels rather than budget motels or hostels, and may name specific merchants for comparison. In that case, some (but not all) of the peer group may be made up of the client’s suggested entities, so long as the client does not know which or how many.

# Control 3.4: Metrics About a Mobile Payment or Digital Wallet Provider’s Performance, and Metrics Reported to Mobile Payment or Digital Wallet Providers, Require Case-by-Case Privacy Review

We treat mobile payment or digital wallet providers like Apple and Google, and transactions that take place through digital wallets, differently from other clients and transactions because those providers are not a financial institutions or merchants, and our Rules do not give them the right to see transactions that occurred though their technology. Additionally, our agreements with certain providers may contractually limit the types of metrics we may report to them or about them.

**Do not** disclose metrics about a mobile payment or digital wallet provider’s performance to an issuer, acquirer, or merchant, without obtaining Privacy review.

**Do not** disclose metrics about an issuer, acquirer, or merchant’s performance to a mobile payment or digital wallet provider, without obtaining Privacy review.

These limitations mean that Mastercard cannot provide a digital wallet provider with benchmark metrics comparing issuer, acquirer, or merchant performance with a benchmarked group of digital wallets.

If you need to deliver metrics related to digital wallets, consider these alternatives:

* Reframing the metric so that it includes all contactless payments.
* Creating a deliverable that describes the impact digital wallet engagement has had on payment card usage, e.g., a “lift analysis” showing growth rates in cardholder engagement before and after digital wallet adoption, or a comparison showing consumer spend insights for consumers who adopted digital wallets versus similar consumers who did not.