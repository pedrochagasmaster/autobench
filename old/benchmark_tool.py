import pandas as pd
import re 
from sklearn.preprocessing import StandardScaler
import numpy as np
import itertools
import argparse
import pypyodbc
import os
import json
from datetime import datetime

# Define a new Python class with functions and attributes
class AAnF_Benchmark():
    # Constructor to initialize attributes
    def __init__(self, 
                 iss_name ,
                 iss_var_name = "Iss_Parent_ICA_Code_Name",
                 breaks       = ["General" , "DOM", "XB", "CNP", "CP"] , 
                 cnt_amt_flag = "Cnt"  , 
                 decline_flag = False
                ):
        self.iss_name      = iss_name
        self.iss_var_name  = iss_var_name
        self.breaks        = breaks
        self.cnt_amt_flag  = cnt_amt_flag
        self.decline_flag  = decline_flag

        self.df_input      = pd.DataFrame()
        self.df_input_fraud = pd.DataFrame()
        self.df_breaks     = pd.DataFrame()
        
        self.compare_dist  = pd.DataFrame()
        self.peer_distances = pd.DataFrame()
        

    # Method to display the attributes
    def display_attributes(self):
        print(f"iss_name     : {self.iss_name}")
        print(f"iss_var_name : {self.iss_var_name}")
        print(f"breaks       : {self.breaks}")
        print(f"cnt_amt_flag : {self.cnt_amt_flag}")

    # Method to update the attributes
    def update_attributes(self, 
                          breaks = None , 
                          cnt_amt_flag = None , 
                          dict_compare = None 
                         ):

        if breaks is not None: 
            self.breaks = breaks
        
        if cnt_amt_flag is not None: 
            self.cnt_amt_flag = cnt_amt_flag

        if dict_compare is not None: 
            self.dict_compare = dict_compare

    def df_2_input(self, 
                   df_source , 
                     dict2convert= None,   
                     agg_by = "Issuer Name" # Aggregate by columns  
                    ): 

        df = df_source.copy()

        if dict2convert is None: # base dictionary  
            dict2convert = {"XB"         : "Cross_Border" , 
                            "DOM"        : "Domestic" , 
                            "Approved"   : "Auth_Approved" , 
                            "Total"      : "Auth_Total_Net_Tran", 
                            "Fraud_Tran" : "Fraud", 
                            "Fraud_Amt_USD" : "Fraud_Amt",
                            
                            "General_Approved_Cnt" : "Total_Approved_Cnt", 
                            "General_Total_Cnt"    : "Total_Total_Cnt", 
                            "General_Approved_Amt" : "Total_Approved_Amt", 
                            "General_Total_Amt"    : "Total_Total_Amt"   ,
                            "General_Fraud_Cnt"    :  "Total_Fraud_Cnt",
                            "General_Fraud_Amt"    : "Total_Fraud_Amt"  }
        
        iss_name_var      = self.iss_var_name.replace( " ", "_")
        breaks            = self.breaks
        count_amount_flag = self.cnt_amt_flag

        df.columns = df.columns \
            .str.replace( "_cnt" , "_Cnt") \
            .str.replace( "_amt" , "_Amt")

        metric_cols = [ col for col in df.columns if re.search(  "_Cnt|_Amt" , col ) ] 
        df[metric_cols] = df[metric_cols].apply(pd.to_numeric)
        #print( df.dtypes )
        
        if agg_by is not None:
            df = df.groupby( agg_by ).sum( numeric_only=True ).reset_index()

        col_names = df.columns
        
        # Ajusted name columns 
        for k,v in dict2convert.items():
            if k.find("General_") < 0 :
                col_names = col_names.str.replace(  v, k, regex=True)
        
        # Last columns as Full total values 
        for k,v in dict2convert.items():
            if k.find("General_") >= 0 :
                col_names = col_names.str.replace( v + ".*", k, regex=True)
                
        df.columns = col_names 
    
        df.rename( columns = { iss_name_var : "Issuer Name" } , inplace = True)
        df.fillna( 0 , inplace = True)



        self.df_input = df 
        
        print_msg  = " >> DF input values in df_input"
        return print( print_msg )
        
    def cube_2_df_inputs(self, 
                         file_dir    = None ,
                         sheet_name  = "Authz",
                         range_data  = [8,12,1], # start and end header, start col with data
                         dummy_fraud = True, 
                         dict2convert= None, 
                         agg_by = "Issuer Name" # Aggregate by columns  
                        ): 

        if dict2convert is None: # base dictionary  
            dict2convert = {"XB"         : "Cross_Border" , 
                            "DOM"        : "Domestic" , 
                            "Approved"   : "Auth_Approved" , 
                            "Total"      : "Auth_Total_Net_Tran", 
                            "Fraud_Tran" : "Fraud", 
                            "Fraud_Amt_USD" : "Fraud_Amt",
                            
                            "General_Approved_Cnt" : "Total_Approved_Cnt", 
                            "General_Total_Cnt"    : "Total_Total_Cnt", 
                            "General_Approved_Amt" : "Total_Approved_Amt", 
                            "General_Total_Amt"    : "Total_Total_Amt"   ,
                            "General_Fraud_Cnt"    :  "Total_Fraud_Cnt",
                            "General_Fraud_Amt"    : "Total_Fraud_Amt"  }
        
        iss_name_var      = self.iss_var_name.replace( " ", "_")
        breaks            = self.breaks
        count_amount_flag = self.cnt_amt_flag
        
        df = pd.read_excel(file_dir, sheet_name= sheet_name )
        
        # Concatenate all values for each column
        col_names = df.iloc[ range_data[0]:range_data[1] , range_data[2]: ].astype( str )
    
        col_names = col_names.apply(lambda row:row.replace('nan', method='ffill') , axis=1 )
        col_names.replace(to_replace=" ", value='_', regex=True, inplace = True)
        #col_names.replace(to_replace="\d{1}_([CP|CNP])_", value='{1}', regex=True, inplace = True)

        # Ajusted name columns 
        for k,v in dict2convert.items():
            if k.find("General_") < 0 :
                col_names.replace( v, k, regex=True, inplace = True)
        # col_names.replace(to_replace="Cross_Border", value='XB', regex=True, inplace = True)
        # col_names.replace(to_replace="Domestic", value='DOM', regex=True, inplace = True)
        
        # col_names.replace(to_replace="Auth_Approved", value='Approved', regex=True, inplace = True)
        # col_names.replace(to_replace="Auth_Total_Net_Tran", value='Total', regex=True, inplace = True)

        #  # Fraude changes 
        # col_names.replace(to_replace="Fraud_Tran", value='Fraud', regex=True, inplace = True)
        # col_names.replace(to_replace="Fraud_Amt_USD", value='Fraud_Amt', regex=True, inplace = True)
        
        concatenated_values = col_names.apply(lambda col: '_'.join(col), axis=0)
        concatenated_values.replace( to_replace="nan_|_nan", value='', regex=True, inplace = True)
        
        # Last columns as Full total values 
        for k,v in dict2convert.items():
            if k.find("General_") >= 0 :
                concatenated_values.replace( v + ".*", k, regex=True, inplace = True)
                
        # concatenated_values.replace( "Total_Approved_Cnt.*", "General_Approved_Cnt", regex=True, inplace = True)
        # concatenated_values.replace( "Total_Total_Cnt.*"   , "General_Total_Cnt", regex=True, inplace = True)

        # concatenated_values.replace( "Total_Approved_Amt.*", "General_Approved_Amt", regex=True, inplace = True)
        # concatenated_values.replace( "Total_Total_Amt.*"   , "General_Total_Amt", regex=True, inplace = True)

        # concatenated_values.replace( "Total_Fraud_Cnt.*"   , "General_Fraud_Cnt", regex=True, inplace = True)
        # concatenated_values.replace( "Total_Fraud_Amt.*"   , "General_Fraud_Amt", regex=True, inplace = True)

        df = df.iloc[ range_data[1]:-1 , range_data[2]: ] # Staring data and drop Gran Total row
        df.columns = concatenated_values.values 
    
        df.rename( columns = { iss_name_var : "Issuer Name" } , inplace = True)
        df.fillna( 0 , inplace = True)

        print_msg = ""
        
        metric_cols = [ col for col in df.columns if re.search(  "_Cnt|_Amt" , col ) ] 
        print( len(metric_cols)  )
        #print( len(df.columns) )
        df[metric_cols] = df[metric_cols].apply(pd.to_numeric)
        #print( df.dtypes )
        
        if agg_by is not None:
            df = df.groupby( agg_by ).sum( numeric_only=True ).reset_index()
        
        if sheet_name.find("Authz") >= 0:
            self.df_input = df
            print_msg  = " >> Authz input values in df_input"
        elif sheet_name.find( "Fraud" ) >= 0:
            self.df_input_fraud = df
            print_msg  = " >> Input values in df_input and df_input_fraud"

        return print( print_msg )

    def join_fraud( self ): 

        pattern_find = ".*Fraud_.*" + self.cnt_amt_flag + ".*"
        col_fraud = [ col for col in self.df_input_fraud.columns if re.match( pattern_find, col ) is not None ]
        col_fraud = [ "Issuer Name" ] + col_fraud
        df_join_fraud = self.df_input \
            .merge(self.df_input_fraud[ col_fraud ] ,
                   on = "Issuer Name" ,
                   how='left')
        
        self.df_input = df_join_fraud

        return print( " >> Fraud values added in df_input" )
        
    
    def df_2_breaks(self,  
                    dummy_fraud = True , 
                    v_break = "Approved" # Change v_break by Approved or Fraud that column use to balance the Benchmark 
                    #metric_columns = ["General_Approved_Cnt","General_Total_Cnt"]
                   ):
        
        count_amount_flag = self.cnt_amt_flag
        
        breaks = self.breaks
        
        df = self.df_input
        df_breaks = df[["Issuer Name"] ].copy()

        total_declined = [ col for col in df.columns if col.find( "General_Declined_" + count_amount_flag ) >= 0 ]
        total_declined = df[ total_declined ].sum( axis = 1) 
        
        for i,break_name in enumerate( breaks ) :
            df_temp = pd.DataFrame()       
        
            pattern_find = ".*" + break_name.replace( "_", ".*") + ".*"
            break_cols = [ col for col in df.columns if re.match( pattern_find, col ) is not None ]  

            if not self.decline_flag :

                v_metric = [ col for col in break_cols if col.find( "_" + v_break + "_" + count_amount_flag ) >= 0 ]  
                approved = [ col for col in break_cols if col.find( "_Approved_" + count_amount_flag ) >= 0 ] 
                total    = [ col for col in break_cols if col.find( "_Total_" + count_amount_flag ) >= 0 ]
                fraud    = [ col for col in break_cols if col.find( "_Fraud_" + count_amount_flag ) >= 0 ] # ajusted with fraud
                
                break_name = break_name + "_" + count_amount_flag
                
                df_temp[ "v_" + break_name + "_br" + str(i)  ] = df[ v_metric ].sum( axis = 1)
                df_temp[ break_name + "_tl" + str(i)  ] = df[ total ].sum( axis = 1)
                df_temp[ break_name + "_ap" + str(i)  ] = df[ approved ].sum( axis = 1)
            else: 
                approved = [ col for col in break_cols if col.find( "_Declined_" + count_amount_flag ) >= 0 ]
                
                break_name = break_name + "_" + count_amount_flag

                df_temp[ "v_" + break_name + "_br" + str(i)  ] = df[ approved ].sum( axis = 1)
                df_temp[ break_name + "_ap" + str(i)  ] = df[ approved ].sum( axis = 1)
                df_temp[ break_name + "_tl" + str(i)  ] = total_declined
        
            if not dummy_fraud:
                df_temp[ break_name + "_fr" + str(i)  ] = df[ fraud ].sum( axis = 1)
            else:
                df_temp[ break_name + "_fr" + str(i)  ] = 1
    
            df_breaks = df_breaks.join( df_temp, how = "left" )

        self.df_breaks = df_breaks
        
        return print( " >> Breaks calculated in df_breaks" )

    def metrics_2_compare(self, 
                          dict_compare = None ,
                          pattern_cols = "_tl\d+" # It could change for fraud columns 
                          ):

        df = self.df_breaks # you should run cube_df_input() to calculate 

        if dict_compare is None: 
            dict_compare = self.dict_compare
        
        selected_total_cols = [col for col in df.columns if re.findall( pattern_cols, col ) ]
        df_filter = df[ selected_total_cols ].copy()
        compare_dist = pd.DataFrame()
        
        dic_names_cols = {}
        
        for total_col,perc_compare in dict_compare.items():
            for col_metric in perc_compare:
                pattern_name = col_metric.replace( "Perc_", "" )
                dic_names_cols[ col_metric ] = [ col for col in df_filter.columns if col.startswith( pattern_name )]
    
        for total_col, perc_compare in dict_compare.items():
            for k in perc_compare: 

                if k.find( "Perc_" ) >= 0:
                    compare_dist[ k ]  = df_filter[ dic_names_cols[ k ] ].sum(axis = 1) / df_filter[ total_col ]
                else: 
                    compare_dist[ k ]  = df_filter[ dic_names_cols[ k ] ].sum(axis = 1) 
    
        compare_dist.fillna( 0, inplace = True)

        self.compare_dist = compare_dist
        
        return " >> Distance to compare in df compare_dist "

    def get_peer_distances(self, 
                           n_closest    = 10,
                           dict_compare = None,
                           scale_flag   = False  ):

        iss_target = self.iss_name
        index_bank = self.df_input[ self.df_input[ 'Issuer Name'] == iss_target ].index
        self.dict_compare = dict_compare
        
        self.metrics_2_compare( dict_compare )

        comparison_metrics = self.compare_dist.copy()
        
        # Calculating distances
        if scale_flag:
            scaler = StandardScaler(with_mean = True , with_std  = True)
            scaled_metrics = \
                pd.DataFrame(scaler.fit_transform(comparison_metrics) ,
                             index = comparison_metrics.index, 
                             columns = comparison_metrics.columns
                            )
        else: 
            scaled_metrics = comparison_metrics.copy()

        self.compare_dist = scaled_metrics.drop( index_bank )
        client_df = scaled_metrics.loc[ index_bank  ]
        perc_compare = [item for sublist in self.dict_compare.values() for item in sublist]
                
        compare_rows   = self.compare_dist.copy()
        row_to_compare = client_df
        
        peer_distances = pd.DataFrame( index = compare_rows.index)
        peer_distances["distance"] = np.sqrt(((compare_rows.values - row_to_compare.values)** 2).sum(axis=1))
        
        # Filtering by the most similar n banks
        self.peer_distances = peer_distances.nsmallest(n_closest, 'distance')
                
        return print(" >> Distance with peers in peer_distances")

    def get_initial_df(self):
         self.initial_df = self.df_breaks\
            .join( self.peer_distances , how = "inner" ) \
            .sort_values( "distance")

############################# --- End of class --- ###########################################  

def format_float(number):
    return f'{number:.2f}'

# Function: Benchmark by monthly
def bm_monthly(client_name   = None ,
               client_name_short = None ,
               df_monthly    = None ,
               metric_namne  = None ,
               tupple_wigths = None ,
               month_var     = "Year_Month" , 
               selected_comb = 1 , 
               bic_ap_rate   = .85, 
               bic_fr_rate   = .15
              ):
        
    n=selected_comb-1 
    
    search_value = metric_namne
    results = list(filter(lambda x: x[0] == search_value, tupple_wigths))
    
    for name, list_df in results:
        patterns = r'_br|_tl|_ap' # Define the patterns where n value have to be extract
        regex = re.compile(r'({0})(.+)'.format(patterns))
        match = regex.search(name)
        nMetric = match.group(2) # Get the text after the pattern to get the number of the n metric value
        metrici = nMetric
        #print('Metrici:' + str(metrici))
        # Define column name endings to search for
        endings = ['Name', month_var ,'_tl'+metrici,'_ap'+metrici,'_fr'+metrici , "Factor_Used" ]
        #print('Endings:' + str(endings))
        
        pattern = '$|'.join(endings)+'$' # Create a regex pattern to match the column names
        summary_df = list_df[n].filter(regex=pattern).copy()
        
        if "Factor_Used" not in summary_df.columns :
            summary_df[ "Factor_Used"] = 1 # Default values
        
        # v_General_Cnt_br0	General_Cnt_tl0	General_Cnt_ap0	General_Cnt_fr0
        #metrics = ["v_General_Cnt_br0", "General_Cnt_tl0" ,"General_Cnt_ap0" , "General_Cnt_fr0" ]
        #cols = ["Issuer Name", "month_var", "v_General_Cnt_br0", "General_Cnt_tl0" ,"General_Cnt_ap0" , "General_Cnt_fr0" ]
        
        df_peers = df_monthly.filter(regex=pattern)   \
            .merge(summary_df[ ["Issuer Name", "Factor_Used"] ] ,
                   on = "Issuer Name" ,
                   how = 'inner')
    
        metrics = [ c for c in df_peers.columns if c not in ["Issuer Name", month_var, "Factor_Used"] ]
        df_peers[metrics] = df_peers[metrics].apply(lambda x: x * df_peers['Factor_Used'])

        ap_name = next((col for col in df_peers.columns if col.endswith('_ap'+metrici)), None)
        tl_name = next((col for col in df_peers.columns if col.endswith('_tl'+metrici)), None)
        fr_name = next((col for col in df_peers.columns if col.endswith('_fr'+metrici)), None)
        #print(ap_name)
        #print(tl_name)
        #print(fr_name)
        # Calculate additional metrics and add them to the summary DataFrame - apr_rate, frd_bps
        df_peers['apr_rate'] = df_peers[ap_name]/df_peers[tl_name]
        df_peers['frd_bps']  = df_peers[fr_name]/df_peers[ap_name] * 1e4
        
        df_peers_bmk = df_peers.groupby( month_var )\
                        .agg(apr_sum = (ap_name ,'sum') , 
                             frd_sum = (fr_name ,'sum' ) , 
                             tot_sum = (tl_name ,'sum')
                            ) \
                        .assign(apr_rate = lambda x: x['apr_sum'] / x['tot_sum']  ,
                               frd_bps  = lambda x: x['frd_sum'] / x['tot_sum'] * 1e4
                              ) \
                        .reset_index()
    
        df_peers_bic = df_peers.groupby( month_var )\
                        .agg(apr_rate = ( 'apr_rate', lambda x: x.quantile(bic_ap_rate) ) , 
                             frd_bps =  ('frd_bps', lambda x: x.quantile( bic_fr_rate ) ) , 
                            ) \
                        .reset_index()

        #**{f'{col}': (col, lambda x: x.sum()) for col in metrics} , # sum columns in list

        nMetric_str = ("00" + str( nMetric ) )[-2:] + "_" 
        df_peers_bmk[ "Break" ] =  nMetric_str + metric_namne
        df_peers_bic[ "Break" ] =  nMetric_str + metric_namne
        
        df_peers_bmk[ "Issuer Name" ] = "1-Peers" 
        df_peers_bic[ "Issuer Name" ] = "2-BiC"
        
        df_client = df_monthly[ df_monthly[ "Issuer Name"] == client_name  ].filter(regex=pattern)
        
        ap_name = next((col for col in df_client.columns if col.endswith('_ap'+metrici)), None)
        tl_name = next((col for col in df_client.columns if col.endswith('_tl'+metrici)), None)
        fr_name = next((col for col in df_client.columns if col.endswith('_fr'+metrici)), None)
        #print(ap_name)
        #print(tl_name)
        #print(fr_name)
        # Calculate additional metrics and add them to the summary DataFrame - apr_rate, frd_bps
        df_client['apr_rate'] = df_client[ap_name]/df_client[tl_name]
        df_client['frd_bps']  = df_client[fr_name]/df_client[ap_name]*10000
        
        df_client[ "Issuer Name" ] = client_name_short
        df_client[ "Break" ]       = nMetric_str + metric_namne

        selected_cols = ["Issuer Name", month_var,
                         "apr_rate","frd_bps",
                         "Break"] 
        
        
        return pd.concat( [df_client[    selected_cols] ,  
                           df_peers_bmk[ selected_cols] , 
                           df_peers_bic[ selected_cols] ])



# Function to trim the last n rows from a DataFrame
def trim_last_n_rows(df, n):
    return df.iloc[:-n] if n < len(df) else df.iloc[0:0]  # Return all rows except the last n rows or Return an empty DataFrame if n is greater than or equal to the length of df


# Function to remove columns ending with '_Percentage' from a DataFrame
def remove_columns_ending_with_percentage(df):
    return df.loc[:, ~df.columns.str.endswith('_Percentage')] # Use boolean indexing to select columns that do not end with '_Percentage' and Return the DataFrame with selected columns

# This function create the valid combinations for a possible benchmark. 
# It returns a list of df with the suggested peers for benchmark in the specific var break. Please note this functions excludes the peers that does not comply with the % max.
# The function recieve as parameter:
# - initial_df: This the resulting df from the csv we inputed with all the possible peers for evaluation. You can refer to the section: Data Ingest and Variable selection, for more details.
# - num_participants: It´s the fixed amount of peers we will include in the combinations. Based on the privacy rules it can be (4 (merchants only), 5, 6, 7, 10)
# - max_rule_percentage: It´s the maximun percentage that each peer can represent in the suggested combination. Based on the privacy rules it can be (25, 30, 35, 40)
# - num_combinations: The numbers of suggested different combination of peers we wanto to get
# - vars_to_eval: Variables, generally by break, we want to evalue. Usually: general view, Cross Border, Domestic, Card Present, Card No Preset, Debit, Credit. etc.
def get_valid_combinations(initial_df, num_participants, max_rule_percentage, num_combinations, vars_to_eval):
    if num_combinations!=1:
        num_combinations = num_combinations #- 1
    # List to store valid combinations
    valid_combinations = []

    # Step 1: Filter out rows where any of the vars_to_eval is null/NaN or 0
    mask = initial_df[vars_to_eval].notnull().all(axis=1) & (initial_df[vars_to_eval] != 0).all(axis=1)
    initial_df_filtered = initial_df[mask]
    
    # Generate all possible combinations of the given quantity
    combinations = itertools.combinations(initial_df_filtered.itertuples(index=False, name=None), num_participants)
    
    # Loop that iterated over all the combinations, it filters the combinations based on the max percentage condition
    for combo in combinations:
        combo_df = pd.DataFrame(combo, columns=initial_df_filtered.columns) # Create a DataFrame from the current combination with the same columns as the original df
        for col in vars_to_eval: # Loop through each variable to evaluate
            combo_total = combo_df[col].sum() # Calculate the total sum of the current column. This to evaluates the %s compliance
            combo_df[f'{col}_Percentage'] = (combo_df[col] / combo_total) * 100
            # Calculate the percentage of each value in the current column and add it as a new column
        if all(combo_df[f'{col}_Percentage'].max() < max_rule_percentage for col in vars_to_eval): # Check if the max % of each column is less than the specified max_rule_percentage
            valid_combinations.append(combo_df) # Add the combination DataFrame (combo_df) to the list of valid_combinations
            if len(valid_combinations) == num_combinations: # Check if the desired number of valid combinations is reached
                return valid_combinations
                
    # If the number of combinations found is less than num_combinations
    if len(valid_combinations) < num_combinations:
        print("Unable to find more combinations.")
    
    return valid_combinations # Returns the valid combinations found.

def get_valid_combinations_for_weighting(initial_df, num_participants, max_rule_percentage, num_combinations, vars_to_eval):
    if num_combinations!=1:
        num_combinations = num_combinations #- 1
    # List to store valid combinations
    valid_combinations = []

     # Step 1: Filter out rows where any of the vars_to_eval is null/NaN or 0
    mask = initial_df[vars_to_eval].notnull().all(axis=1) & (initial_df[vars_to_eval] != 0).all(axis=1)
    initial_df_filtered = initial_df[mask]
    
    # Generate all possible combinations of the given quantity
    combinations = itertools.combinations(initial_df_filtered.itertuples(index=False, name=None), num_participants)

    # Get the first n combinations
    first_n_combinations = list(itertools.islice(combinations, num_combinations))

    # Convert each combination (tuple) into a DataFrame
    for combo in first_n_combinations:
        combo_df = pd.DataFrame(combo, columns=initial_df_filtered.columns) # Create a DataFrame for each combination
        valid_combinations.append(combo_df) # Add the DataFrame to the list

    # Now first_n_combinations contains only the first n combinations
    return valid_combinations

# Function to validate that the remaining rows minus after removing the last/first n rows are the same across a list of DataFrames and return ONLY the distinct trimmed DataFrames.
# Parameters:
# - dfs: List of the dfs to evaluate
# - n: number of columns to be trimmed
def validate_dfs_are_distinct(dfs, n):
    # Remove columns ending with '_Percentage' from each DataFrame in dfs
    modified_dfs = [remove_columns_ending_with_percentage(df) for df in dfs]
    
    # Trim the last n rows from each modified DataFrame
    trimmed_dfs = [trim_last_n_rows(df, n) for df in modified_dfs]

    # Use the first trimmed DataFrame as the reference
    reference_df = trimmed_dfs[0]
    
    # Check if all trimmed DataFrames are equal to the reference DataFrame
    all_equal = all(reference_df.equals(df) for df in trimmed_dfs)
    
    # Collect original DataFrames corresponding to distinct trimmed DataFrames
    distinct_original_dfs = []
    seen = set()
    for original_df, trimmed_df in zip(dfs, trimmed_dfs):
        # Convert the trimmed DataFrame to a tuple of tuples to make it hashable
        df_tuple = tuple(map(tuple, trimmed_df.values))
        if df_tuple not in seen:
            seen.add(df_tuple)
            distinct_original_dfs.append(original_df)

    # Remove columns ending with '_Percentage' from the distinct original DataFrames
    distinct_original_dfs_nopercentage = [remove_columns_ending_with_percentage(df) for df in distinct_original_dfs]
    # Return a tuple containing whether all trimmed DataFrames are equal and the distinct original DataFrames without '_Percentage' columns
    return all_equal, distinct_original_dfs_nopercentage


# Function that will include the excluded peers (because exceed the % or does not comply with the rules) in the distinct combination, for later weight it.
# It receives by parameter:
# - comb: distinct comb that will include the excluded peers
# - vars_to_eval: variable being evaluated. Used for sorting the df at the end.
# - num_participants: numbers of peers needed for the final combination
# - filtered_top_excluded_peers: list of peers that were not used because did not comply with the % rule and are above the max peer used
# - exclude_last: Optional parameter, set by default to true. It will indicate if we exclude the last n rows or we exclude the list of peer_to_exclude
# - peer_to_exclude: Optional parameter. Used if exclude_last is False. Must contain a list of preferred peers to exclude.
def fit_excluded_peers(comb, vars_to_eval, excl_peers, num_participants, exclude_last=True, peer_to_exclude=['']):
    n_drop_peer = excl_peers['Issuer Name'].count() # Count the number of excluded peers
    # If the number of excluded peers exceeds the number of participants
    if n_drop_peer > num_participants:
        exceed = n_drop_peer - num_participants # Calculate the excess number of peers
        n_drop_peer = num_participants # Adjust the number of peers to drop
        excl_peers = excl_peers.drop(excl_peers.tail(exceed).index) # Drop the excess number of peers from the list of peers that were excluded
    comb = comb.loc[:, ~comb.columns.str.endswith('_Percentage')] # Delete columns of % calculated in previous steps
    # If exclude_last is True, drop the last n_drop_peer rows from the combination DataFrame, so we can fit the excluded peers there
    if exclude_last:
        comb = comb.drop(comb.tail(n_drop_peer).index)
    else:
        # Otherwise, exclude the peers listed in peer_to_exclude passed by parameter
        comb = comb[~comb['Issuer Name'].isin(peer_to_exclude)]
    # Concatenate the combination DataFrame with the excluded peers DataFrame
    concat_df = pd.concat([comb,excl_peers], ignore_index=True)
    # Sort the concatenated DataFrame by the selected column(s) in descending order and reset the index
    concat_df = concat_df.sort_values(vars_to_eval, ascending=False).reset_index(drop=True)
    return concat_df # Return the final concatenated and sorted DataFrame

# Function that adjusts (weights) the variable being evaluated to comply with the max_ percentage allowed. It takes as parameters:
# - data: df to be evaluated and weight
# - variable_name: the variable that we are evaluating and needs the adjusment
# - threshold_percent: the max percentage the variable will be adjusted to. Set by default to 25%
def adjust_values(data, variable_name, threshold_percent=25):
    """
    Adjusts values in a DataFrame column to comply with a maximum percentage threshold.
    This version is vectorized to be more efficient and avoid SettingWithCopyWarning.
    """
    # --- FIX IS HERE ---
    # Proactively convert the column to a float type to accept decimal values.
    # This resolves the FutureWarning without losing precision.
    if pd.api.types.is_integer_dtype(data[variable_name]):
        data[variable_name] = data[variable_name].astype('float64')
    # --- END OF FIX ---

    # Convert threshold_percent to a decimal, subtracting a small amount for a strict '<' comparison
    threshold = (threshold_percent / 100) - 0.0001
    
    while True:
        total = data[variable_name].sum()
        
        if total == 0:
            break
            
        max_allowed = total * threshold
        
        exceeded_mask = data[variable_name] > max_allowed

        if not exceeded_mask.any():
            break
        
        # Now the assignment is safe because the column dtype is already a float
        data.loc[exceeded_mask, variable_name] = max_allowed
        
    return data

# Function to get a df with the peers that are above the max num (amount, txns, rate) of the list of peers already used. Parameters:
# - selected_vars: Variables, generally by break, we want to evalue. Usually: general view, Cross Border, Domestic, Card Present, Card No Preset
# - initial_df: This the csv we inputed with all the possible peers for evaluation. You can refer to the section: Data Ingest and Variable selection, for more details.
# - result_df: Result of function get_valid_combinations. It´s a list of dfs with the resulting combinations suggested for the benchmark
def get_max_issuer_used(var_names, initial_df, result_df):
    df_to_append = pd.DataFrame() # Create an empty DataFrame for temporary storage
    for var in var_names: # Loop through each variable name in the var_names list
        max_value = 0 # Initialize the max_value variable to 0. This max_value will have the max num (amount, txns, rate) of the list of peers already used.
        for df_res in result_df: # Loop through each DataFrame in the result_df list
            current_max = df_res[var].max() # Get the maximum value of the current variable in the current DataFrame
            if current_max > max_value: # Update max_value if the current_max is greater
                max_value=current_max
        df_to_append = initial_df[initial_df[var]>max_value] # Filter the initial DataFrame to include rows where the current variable's value is greater than max_value
    return df_to_append.drop_duplicates() # Drop duplicate rows from the df_to_append DataFrame and return it

def evaluate_rules(tuple_dfs, rule):
    results = []
    if not isinstance(tuple_dfs, list):
        tuple_dfs = [tuple_dfs]
    for name, dfs in tuple_dfs:
        for idx, df in enumerate(dfs):
            # Calculate percentages
            total_amount = df[name].sum()
            df['Percentage'] = df[name] / total_amount * 100
            
            # Evaluate rules
            if rule==(6,31):
                num_7_percent = (df['Percentage'] >= 7).sum()
                if not num_7_percent >= 3:
                    results.append(f"DataFrame {name} in combination {idx + 1}: Rules not satisfied. 7% players {num_7_percent}")
            elif rule==(7,36):
                num_15_percent = (df['Percentage'] >= 15).sum()
                num_8_percent = (df['Percentage'] >= 8).sum()
                if not num_15_percent >= 2 and not num_8_percent > 0:
                    results.append(f"DataFrame {name} in combination {idx + 1}: Rules not satisfied. 15% players {num_15_percent}, 8% players {num_8_percent}")
            elif rule==(10,41):
                num_20_percent = (df['Percentage'] >= 20).sum()
                num_10_percent = (df['Percentage'] >= 10).sum()
                two_20_percent = num_20_percent >= 2
                additional_10_percent = (df['Percentage'] >= 10).sum() > num_20_percent
                if not (two_20_percent and additional_10_percent):
                    results.append(f"DataFrame for break {name} in combination {idx + 1}: Rules not satisfied. 20% players {num_20_percent}, 10% players {num_20_percent-num_10_percent}")
    return results

def compare_result_dfs_by_column(tuples_list, column_name):
    # Store the index of each column data for comparison
    column_data_map = {}
    
    # Iterate through the list of tuples
    for i, (name, result_dfs) in enumerate(tuples_list):
        for j, df in enumerate(result_dfs):
            # Check if the item is a DataFrame
            if isinstance(df, pd.DataFrame):
                # Extract the specified column and convert it to a tuple for comparison
                if column_name in df.columns:
                    column_data = tuple(df[column_name])
                    
                    # Check if the column data has been seen before
                    if column_data in column_data_map:
                        column_data_map[column_data].append((name, i, j))
                    else:
                        column_data_map[column_data] = [(name, i, j)]
                else:
                    print(f"Column '{column_name}' not found in DataFrame for '{name}' at index {i}, DataFrame {j}.")
            else:
                print(f"Item at index {i}, DataFrame {j} for '{name}' is not a DataFrame.")
    
    # Print the results
    for column_data, name_indices in column_data_map.items():
        if len(name_indices) > 1:
            tuple_names = [tuples_list[i][0] for _, i, _ in name_indices]  # Get the tuple names
            print(f"Matching '{column_name}' column found for tuples: {tuple_names}")
            print(f"Issuer Names: {column_data}")

def evaluate_var_if_not_comb_found(initial_df, num_combinations, rules, var, exclude_rule):
    filtered_rules = [tup for tup in rules if tup != exclude_rule]
    var_names = [var]
    for rule in filtered_rules:
        part, perc = rule
        print('EVALUATING ' + var + ' under rule ' + str(rule))
        result_df = get_valid_combinations(initial_df, part, perc, num_combinations, var_names) # Executes the function get_valid_combinations which returns 
        #a list of dfs with the resulting combinations. For more details of the function, go to the Functions section --> Part 1 - Combinations no Weights
        if result_df:
            return result_df, perc
    return [], 0


# This is the main function that orquestrates the process of getting the proposal of peers combinations. 
# It returns list_final_result, which is a list of tuples containing the combinations. The tuple is structured: (variable being evaluated name, resulting df with the combinations)
# It receives by parameter: 
# - initial_df: This the csv we inputed with all the possible peers for evaluation. You can refer to the section: Data Ingest and Variable selection, for more details.
# - num_participants: It´s the fixed amount of peers we will include in the combinations. Based on the privacy rules it can be (4 (merchants only), 5, 6, 7, 10)
# - max_percentage: It´s the maximun percentage that each peer can represent in the suggested combination. Based on the privacy rules it can be (25, 30, 35, 40)
# - num_combinations: The numbers of suggested different combination of peers we wanto to get
# - vars_to_eval: Variables, generally by break, we want to evalue. Usually: general view, Cross Border, Domestic, Card Present, Card No Preset
def get_combinations_proposed(initial_df, 
                              num_participants,
                              max_percentage, 
                              num_combinations, 
                              vars_to_eval, 
                              rules,
                              issuer_column):
    list_final_result = [] # Initialization of the list of tuples we will return at the end
    applied_other_rule = False
    rule_to_apply = (num_participants, max_percentage)

    # For loop to iterate over each break variable and get suggested combinations
    for idx, var in enumerate(vars_to_eval):
        print('EVALUATING ' + var + ':')
        var_names = [var] # Since the original function recieves a list of variables to evaluate and this loop evaluates individually, we transform it to a list
        result_df = get_valid_combinations(initial_df, num_participants, max_percentage, num_combinations, var_names) # Executes the function get_valid_combinations which returns 
        #a list of dfs with the resulting combinations. For more details of the function, go to the Functions section --> Part 1 - Combinations no Weights

        if not result_df: # In case no combinations are found.
            print('No combinations under rule choose. Weighting: ')
            combinations_to_weight = get_valid_combinations_for_weighting(initial_df, num_participants, max_percentage, num_combinations, var_names)
            for comb_wei in combinations_to_weight:
                original_values = comb_wei.copy()
                data = adjust_values(comb_wei, var, max_percentage) # Execute the functions adjust_values, that will weight the peers that exceed the % rule used. 
                #Returns the df with the adjusted values that complies with the rule (weight values)
                original_values = original_values.set_index("Issuer Name") # Set the "Issuer Name" as the index for the original_values DataFrame
                df_adjusted = data.set_index("Issuer Name") # Set the "Issuer Name" as the index for the data DataFrame, resulting in df_adjusted
                # Divide columns to get factor
                df_adjusted['Factor_Used'] = df_adjusted[var] / original_values[var]
                # Reset index
                df_adjusted = df_adjusted.reset_index()
                total_sum_var = df_adjusted[var].sum() # Calculate the total sum of the specified variable column in df_adjusted
                df_adjusted[var+'_Percentage'] = (df_adjusted[var] / total_sum_var) * 100 # Calculate the percentage of each value in the specified variable column
                # and create a new column with the results
                result_df.append(df_adjusted) # Append the adjusted DataFrame to the result_df list

            if result_df:
                tuple_data = (var, result_df) # Create a tuple with the variable name and the list of result df
                results_rule_Eval = evaluate_rules(tuple_data, rule_to_apply)
                print('1')
                list_final_result.append(tuple_data) # Append the tuple to the list_final_result
                if results_rule_Eval:
                    print('One of combinations does not meet rules. Please review. Details:')
                    for result in results_rule_Eval:
                        print(result)
            else:
                print('No combinations after rule weighting. Evaluating other rules: ')
                applied_other_rule = True
                result_df, new_max_percentage = evaluate_var_if_not_comb_found(initial_df, num_combinations, rules, var, rule_to_apply)
                if not result_df:
                    applied_other_rule = False
                    print('SORRY, no combinations found under any rule :(')
                    continue # Continue to the next iteration variable
        ##-- This Section to evaluate if there´s any peer that was not included because its size and adjust it if any.
        used_peers = [] # List that will contain all the peers already included in the suggested combinations
        for comb in result_df.copy(): 
            used_peers.extend(comb["Issuer Name"].tolist()) # Add the used peers to the list 
        all_peers = initial_df["Issuer Name"].tolist() # Get the list of all the peers from the initial csv
        diff = set(all_peers) - set(used_peers) # Calculate the difference between the set of all_peers and used_peers to find peers that haven't been used yet
        diff_issuers = initial_df[initial_df["Issuer Name"].isin(diff)] # Filter the initial DataFrame to include only the rows where "Issuer Name" is in the diff set
        # Execute the functions that will return the list of peers that were not used because did not comply with the % rule and are above the max peer used
        filtered_top_excluded_peers = get_max_issuer_used(var_names, initial_df, result_df)
        # Get the number of peers that were excluded and can be included
        n_peer = filtered_top_excluded_peers["Issuer Name"].count()
    
        if n_peer == 0: # If the number of peers excluded are 0, then
            tuple_data = (var, result_df) # Create a tuple for the final result. The tuple is structured: (variable being evaluated name, resulting df with the combinations)
            results_rule_Eval = evaluate_rules(tuple_data, rule_to_apply)
            if results_rule_Eval:
                print('One of combinations does not meet rules. Please review.') ## INCLUDE LOGIC TO APPLY OTHER RULE. ENHANCE!
                for result in results_rule_Eval:
                    print(result)
            print('2')
            list_final_result.append(tuple_data) # Append the tuple to the list_final_result
            print('No excluded Peers. Combinations are:')
            for idx, combo in enumerate(result_df): # Loop through each combination in the result DataFrame
                        if 'Distance to Client' not in combo.columns:
                            # Add the column with a dummy value, e.g., 0 or NaN
                            combo['Distance to Client'] = 0  
                        columns_to_select = ["Issuer Name", 'Distance to Client', var, var +'_Percentage'] # Select the columns to display: the variable and its percentage. This to reduce the view columns.
                        combo_sel = combo[columns_to_select]
                
                        # Print the combination index and the selected columns
                        print(f"Combination {idx + 1}:")
                        print(combo_sel)
                        print()
            continue # Continue to the next iteration variable
        #Function to evaluate that the result_df containing the list of dfs with the resulting combinations are not the same after trimming the last n rows, for fitting the excluded peers.
        result, distinct_dfs = validate_dfs_are_distinct(result_df.copy(), n_peer)
        for comb in distinct_dfs.copy(): ## Iterate over all the distinct comb df after the last n rows trimmed
            if (len(result_df) >= num_combinations): ## If we already have all the combinations do not add more even if there are weighted
                tuple_data = (var, result_df) # Create a tuple with the variable name and the list of result df
                results_rule_Eval = evaluate_rules(tuple_data, rule_to_apply)
                print('3')
                list_final_result.append(tuple_data) # Append the tuple to the list_final_result
                continue
            df_test = fit_excluded_peers(comb, vars_to_eval, filtered_top_excluded_peers, num_participants) 
        #and executes the function that will include the excluded peers on the combinations. Return a new df containing the excluded peers. For function details:
            #Go to Part 2. Weights Logic -> fit_excluded_peers(comb, vars_to_eval, excl_peers, num_participants, exclude_last=True, peer_to_exclude=[''])
            original_values = df_test.copy() ## Create a opy of the result df from previous function. 
            #This will be used later to calculate the adjustement made to the variable num, the 'factor'
            if applied_other_rule: # This is to control the max percetage used in case other rule were applied
                data = adjust_values(df_test, var, new_max_percentage) # Execute the functions adjust_values, that will weight the peers that exceed the % rule used. 
                #Returns the df with the adjusted values that complies with the rule (weight values)
            else:
                data = adjust_values(df_test, var, max_percentage) # Execute the functions adjust_values, that will weight the peers that exceed the % rule used. 
                #Returns the df with the adjusted values that complies with the rule (weight values)
            original_values = original_values.set_index("Issuer Name") # Set the "Issuer Name" as the index for the original_values DataFrame
            df_adjusted = data.set_index("Issuer Name") # Set the "Issuer Name" as the index for the data DataFrame, resulting in df_adjusted
            # Divide columns to get factor
            df_adjusted['Factor_Used'] = df_adjusted[var] / original_values[var]
            # Reset index
            df_adjusted = df_adjusted.reset_index()
            total_sum_var = df_adjusted[var].sum() # Calculate the total sum of the specified variable column in df_adjusted
            df_adjusted[var+'_Percentage'] = (df_adjusted[var] / total_sum_var) * 100 # Calculate the percentage of each value in the specified variable column
            # and create a new column with the results
            result_df.append(df_adjusted) # Append the adjusted DataFrame to the result_df list
        tuple_data = (var, result_df) # Create a tuple with the variable name and the list of result df
        results_rule_Eval = evaluate_rules(tuple_data, rule_to_apply)
        print('4')
        list_final_result.append(tuple_data) # Append the tuple to the list_final_result
        if results_rule_Eval:
            print('One of combinations does not meet rules. Please review. Details:')
            for result in results_rule_Eval:
                print(result)
        ## Final output. Print the results:
        print("\nValidated Data:")
        for idx, combo in enumerate(result_df):
            if 'Distance to Client' not in combo.columns:
                # Add the column with a dummy value, e.g., 0 or NaN
                combo['Distance to Client'] = 0  # or you can use pd.NA, np.nan, etc.
            if 'Factor_Used' in combo.columns:
                columns_to_select = ["Issuer Name", 'Distance to Client', var, var +'_Percentage', 'Factor_Used']
            else:
                columns_to_select = ["Issuer Name", 'Distance to Client', var, var +'_Percentage']
            combo_sel = combo[columns_to_select]
            print(f"Combination {idx + 1}:")
            print(combo_sel.sort_values(var, ascending=False))
            print()
    compare_result_dfs_by_column(list_final_result, "Issuer Name") # This line executes the compare_result_dfs_by_column to validate if there os any 
    #combination that can be used in other breaks
    return list_final_result # Return the output for usage

#### Part 5. KPIS calculations

# Function that will calculate the main KPIS for each of the metrics, based on the combination selected. It will return a list with the metric name and the calculated KPIs.
# Takes as Parameters:
# - metric: Name of the metric we will evaluate
# - tuple_final: Resulting list of tuples with all the combinations
# - selected_comb: number of the combination to calculate KPIs for
def get_comb_kpis_v2(metric, tuple_final, selected_comb=1, bic_apr_q = 0.85 ):
    n=selected_comb-1 # Adjust the selected_comb to be zero-indexed
    
    # Search for the tuple with the specified metric
    search_value = metric
    results = list(filter(lambda x: x[0] == search_value, tuple_final))
    if not results: # If no results are found, return an empty list
        return []

    # Process the found results
    for name, list_df in results:
        print('Name:' + str(name))
        patterns = r'_br|_tl|_ap' # Define the patterns where n value have to be extract
        regex_patt = re.compile(r'({0})(.+)'.format(patterns))
        match = regex_patt.search(name)
        nMetric = match.group(2) # Get the text after the pattern to get the number of the n metric value
        metrici = nMetric
        #print('Metrici:' + str(metrici))
        # Define column name endings to search for
        endings = ['Name','_tl'+metrici,'_ap'+metrici,'_fr'+metrici ]
        #print('Endings:' + str(endings))
        
        pattern = '$|'.join(endings)+'$' # Create a regex pattern to match the column names
        summary_df = list_df[n].filter(regex=pattern) # Filter the DataFrame to include only the relevant columns using the regex
        # Identify specific columns in the summary DataFrame
        ap_name = next((col for col in summary_df.columns if col.endswith('_ap'+metrici)), None)
        tl_name = next((col for col in summary_df.columns if col.endswith('_tl'+metrici)), None)
        fr_name = next((col for col in summary_df.columns if col.endswith('_fr'+metrici)), None)
        #print(ap_name)
        #print(tl_name)
        #print(fr_name)
        # Calculate additional metrics and add them to the summary DataFrame - apr_rate, frd_bps
        summary_df['apr_rate']=summary_df[ap_name]/summary_df[tl_name]
        summary_df['frd_bps']=summary_df[fr_name]/summary_df[ap_name]*10000
        print(summary_df)
        # Calculate average and 15th percentile (BIC) values for apr_rate and frd_bps
        avg_apr_rate = summary_df['apr_rate'].mean() #.sum()/summary_df[tl_name].sum()
        bic_apr_rate = summary_df['apr_rate'].quantile(bic_apr_q)
        avg_bps = summary_df[fr_name].sum()/summary_df[ap_name].sum()*10000
        bic_bps = summary_df['frd_bps'].quantile(0.15)
    # Return a list with the metric name and the calculated KPIs, rounded to 2 decimal places
    return [name,round(avg_apr_rate,2),round(bic_apr_rate,2),round(avg_bps,2),round(bic_bps,2)]

def get_comb_kpis(metric, tuple_final, selected_comb=1, bic_apr_q = 0.85 ):
    n = selected_comb - 1
    
    # Search for the tuple with the specified metric
    search_value = metric
    results = list(filter(lambda x: x[0] == search_value, tuple_final))
    if not results:
        return []

    # Process the found results
    for name, list_df in results:
        
        # --- FIX IS HERE ---
        # Check if the list of combinations is empty or if the selected index is out of bounds.
        if not list_df or n >= len(list_df):
            print(f"Warning: Combination #{selected_comb} not available for metric '{name}'. Skipping KPI calculation for this metric.")
            return [] # Return an empty list to signify no KPIs could be calculated for this specific metric.
        # --- END OF FIX ---

        print('Name:' + str(name))
        patterns = r'_br|_tl|_ap'
        regex_patt = re.compile(r'({0})(.+)'.format(patterns))
        match = regex_patt.search(name)
        nMetric = match.group(2)
        metrici = nMetric
        
        endings = ['Name','_tl'+metrici,'_ap'+metrici,'_fr'+metrici, "Factor_Used"]
        pattern = '$|'.join(endings)+'$'
        summary_df = list_df[n].filter(regex=pattern).copy()
        
        ap_name = next((col for col in summary_df.columns if col.endswith('_ap'+metrici)), None)
        tl_name = next((col for col in summary_df.columns if col.endswith('_tl'+metrici)), None)
        fr_name = next((col for col in summary_df.columns if col.endswith('_fr'+metrici)), None)

        if 'Factor_Used' not in summary_df.columns:
            summary_df[ "Factor_Used"] = 1
            
        summary_df[ ap_name ] = summary_df[ ap_name ] * summary_df[ "Factor_Used"]
        summary_df[ tl_name ] = summary_df[ tl_name ] * summary_df[ "Factor_Used"]
        summary_df[ fr_name ] = summary_df[ fr_name ] * summary_df[ "Factor_Used"]

        summary_df['apr_rate']= summary_df[ap_name]/summary_df[tl_name]
        summary_df['frd_bps'] = summary_df[fr_name]/summary_df[ap_name]*10000
        print(summary_df)

        avg_apr_rate  = summary_df[ap_name].sum() / summary_df[tl_name].sum()
        bic_apr_rate  = summary_df['apr_rate'].quantile(bic_apr_q)
        mean_apr_rate = summary_df['apr_rate'].mean()
        
        avg_bps = summary_df[fr_name].sum() / summary_df[ap_name].sum() * 10000
        
        bic_bps = summary_df['frd_bps'].quantile(0.15)
        mean_bps = summary_df['frd_bps'].mean()
        
    # Return a list with the metric name and the calculated KPIs
    return [name,
            round(avg_apr_rate,2),
            round(bic_apr_rate,2),
            round(avg_bps,2),
            round(bic_bps,2),
           ]

def drop_non_defined_metric_words(text,filter_words):
    words = re.findall(r'\b\w+\b', text)  # Find all words in the text
    matched_phrases = []
    for phrase in filter_words:
        if re.search(r'\b' + re.escape(phrase) + r'\b', text):
            matched_phrases.append(phrase)
    filtered_text = ' '.join(matched_phrases)
    return filtered_text

def transform_data_output(trans_df,acrons_df):
    df = trans_df.copy()
    a_df = acrons_df.copy()
    # formating the metric name to be client ready
    df['Metric'] = df['Metric'].str.replace(r'_br.*$', '', regex=True)
    df['Metric'] = df['Metric'].str.replace(r'_tl.*$', '', regex=True)
    df['Metric'] = df['Metric'].str.replace(r'_ap.*$', '', regex=True)
    df['Metric'] = df['Metric'].str.replace(r'_fr.*$', '', regex=True)
    df['Metric'] = df['Metric'].str.replace('v_', '', regex=True)
    for index, row in a_df.iterrows():
        search_value = row['Acronym']
        replacement_value = row['Meaning']
        df['Metric'] = df['Metric'].str.replace(search_value, replacement_value, regex=True)
    df['Metric'] = df['Metric'].str.replace('_', ' ', regex=True)
    metrics_words = set(a_df['Meaning'])
    print(metrics_words)
    df['Metric'] = df['Metric'].apply(drop_non_defined_metric_words,args=(metrics_words,))
    # Create two separate DataFrames for columns B/C and D/E
    df_bc = df[['Metric', 'AVG Aproval Rate', 'BIC Approval Rate']].rename(columns={'AVG Aproval Rate': 'Value_B', 'BIC Approval Rate': 'Value_C'})
    df_de = df[['Metric', 'AVG BPS', 'BIC BPS']].rename(columns={'AVG BPS': 'Value_D', 'BIC BPS': 'Value_E'})

    # Melt each DataFrame to create two rows per original row
    df_bc_peer = df_bc.melt(id_vars='Metric', value_vars=['Value_B', 'Value_C'], var_name='KPI', value_name='Apr_Rate')
    df_de_peer = df_de.melt(id_vars='Metric', value_vars=['Value_D', 'Value_E'], var_name='KPI', value_name='Fraud_BPS')

    # Map 'peer' and 'BIC' to KPI names
    df_bc_peer['KPI'] = df_bc_peer['KPI'].apply(lambda x: 'peer' if x == 'Value_B' else 'BIC')
    df_de_peer['KPI'] = df_de_peer['KPI'].apply(lambda x: 'peer' if x == 'Value_D' else 'BIC')

    # Merge df_bc_peer and df_de_peer on 'A', 'KPI' columns
    final_df = pd.merge(df_bc_peer, df_de_peer, on=['Metric', 'KPI'], how='inner')
    # Sort final_df by column 'A'
    final_df = final_df.sort_values(by=['Metric', 'KPI']).reset_index(drop=True)
    client_row_values = {
    'KPI': "Client",
    'Apr_Rate': 0,
    'Fraud_BPS': 0
    }
    # Get unique values from column A
    unique_metric_values = final_df['Metric'].unique()

    # Append new rows directly to the original dataframe
    for value in unique_metric_values:
        new_row = client_row_values.copy()
        new_row['Metric'] = value
        final_df = final_df.append(new_row, ignore_index=True)

    return final_df


# --- Logging Functions ---
def setup_logging(log_file, args):
    """Creates and initializes the log file with execution parameters."""
    with open(log_file, 'w') as f:
        f.write(f"Benchmark Analysis Log\n")
        f.write(f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*50 + "\n")
        f.write("Execution Parameters:\n")
        for arg, value in vars(args).items():
            f.write(f"  --{arg}: {value}\n")
        f.write("="*50 + "\n\n")

def log_result(log_file, name, df_shape, result):
    """Appends the result of a single break analysis to the log file."""
    with open(log_file, 'a') as f:
        f.write(f"Analysis for: {name}\n")
        f.write(f"  - Dataset Shape: {df_shape[0]} rows, {df_shape[1]} columns\n")
        if result[2] is not None: # Check if a successful combination was found
            f.write(f"  - Status: SUCCESS\n")
            f.write(f"  - Combination Used: #{result[2]}\n")
            f.write(f"  - Peer Group: {result[1]}\n")
        else:
            f.write(f"  - Status: FAILED\n")
            f.write(f"  - Reason: No valid peer combination found that satisfies the benchmark rules.\n")
        f.write("-"*50 + "\n")

# --- Data Processing and Analysis Functions (No changes) ---
def pivot_and_aggregate(df_raw, breaks, rows, columns_pivot, issuer_column):
    break_cols = [issuer_column] + breaks
    columns_to_sum = [f"{col}_cnt" for col in columns_pivot]
    df_pivot = df_raw.groupby(break_cols).agg({col: "sum" for col in columns_to_sum}).reset_index()
    df_pivot_adj = pd.pivot_table(
        df_pivot, index=rows, columns=breaks, values=columns_to_sum, aggfunc="sum"
    ).reset_index().fillna(0)
    df_pivot_adj.columns = df_pivot_adj.columns.to_flat_index().map(lambda x: x[1:] + (x[0],)).map("_".join).str.lstrip("_")
    row_totals = df_pivot_adj.drop(columns=rows).groupby(lambda x: "_".join(x.split('_')[len(breaks):]), axis=1).sum()
    row_totals.columns = [f"General_{col}" for col in row_totals.columns]
    df_pivot_adj = pd.concat([df_pivot_adj[rows], df_pivot_adj.drop(columns=rows), row_totals], axis=1)
    return df_pivot_adj

def prepare_benchmark(df_pivot_adj, break_cols, dict2convert, issuer_column, issuer_name):
    all_cols = df_pivot_adj.columns.drop(issuer_column)
    suffixes_to_remove = [f"_{col}_cnt" for col in ["app", "txn", "fraud"]]
    specific_breaks = set()
    for col in all_cols:
        if not col.startswith("General_"):
            for suffix in suffixes_to_remove:
                if col.endswith(suffix):
                    specific_breaks.add(col.removesuffix(suffix))
                    break
    breaks = ["General"] + sorted(list(specific_breaks))
    benchmark_tool = AAnF_Benchmark(
        iss_name=issuer_name, iss_var_name=issuer_column, cnt_amt_flag="Cnt", breaks=breaks
    )
    benchmark_tool.df_2_input(df_pivot_adj, dict2convert, agg_by=issuer_column)
    benchmark_tool.df_2_breaks(dummy_fraud=False)
    benchmark_tool.get_peer_distances(dict_compare={"General_Cnt_tl0": ["Perc_CNP_Cnt"]})
    benchmark_tool.get_initial_df()
    
    return benchmark_tool

def evaluate_combinations(initial_df, vars_to_eval, rules, num_participants, max_percentage, num_combinations, selected_comb, issuer_column):
    tuple_final = get_combinations_proposed(
        initial_df, num_participants, max_percentage, num_combinations, vars_to_eval, rules, issuer_column
    )
    peer_group_names = []
    if tuple_final:
        first_valid_result = next((tup for tup in tuple_final if tup[1]), None)
        if first_valid_result:
            try:
                selected_df = first_valid_result[1][selected_comb - 1]
                peer_group_names = selected_df["Issuer Name"].tolist()
            except IndexError:
                print(f"Warning: Combination {selected_comb} not found for this break.")
    df_kpis = pd.DataFrame(columns=['Metric', 'AVG Aproval Rate', 'BIC Approval Rate', 'AVG BPS', 'BIC BPS'])
    for var in vars_to_eval:
        result_break = get_comb_kpis(var, tuple_final, selected_comb, bic_apr_q=0.85)
        if not result_break:
            continue
        series_to_append = pd.Series(result_break, index=df_kpis.columns)
        df_kpis = pd.concat([df_kpis, series_to_append.to_frame().T], ignore_index=True)
    return df_kpis, peer_group_names

def balance_peer(df_raw, rows, breaks, columns_pivot, dict2convert, issuer_column, issuer_name,
                 rules, num_combinations, num_participants, max_percentage, selected_comb):
    print(f'\n>> Processing Break: {breaks} | Attempting Combination: {selected_comb}')
    df_raw = df_raw.copy()
    df_pivot_adj = pivot_and_aggregate(df_raw, breaks, rows, columns_pivot, issuer_column)
    benchmark_tool = prepare_benchmark(df_pivot_adj, breaks, dict2convert, issuer_column, issuer_name)
    initial_df = benchmark_tool.initial_df
    initial_df.columns = initial_df.columns.str.strip()
    vars_to_eval = [col for col in initial_df.columns if col.startswith("v_")]
    df_kpis, peer_group = evaluate_combinations(
        initial_df, vars_to_eval, rules, num_participants, max_percentage, num_combinations, selected_comb, issuer_column
    )
    return df_kpis, peer_group

def run_analysis_with_fallback(comb_priority, *args):
    for comb_num in comb_priority:
        df_kpis, peer_group = balance_peer(*args, selected_comb=comb_num)
        if peer_group:
            print(f"--- Success! Found valid peer group with Combination #{comb_num} ---")
            return df_kpis, peer_group, comb_num
    print(f"--- FAILED! No valid peer group found for any combination in priority list: {comb_priority} ---")
    return pd.DataFrame(), [], None

def generate_target_breaks(break_definitions, df_geral, comb_priority):
    target_breaks = {}
    for definition in break_definitions:
        if ":" in definition:
            col1, col2 = definition.split(':')
            unique_values = df_geral[col1].unique()
            for val in unique_values:
                break_name = f"{col1}_{val}_by_{col2}"
                filtered_df = df_geral[df_geral[col1] == val].copy()
                target_breaks[break_name] = ([col2], filtered_df, comb_priority)
        else:
            col1 = definition
            break_name = f"Break_by_{col1}"
            target_breaks[break_name] = ([col1], df_geral, comb_priority)
    return target_breaks

# --- Modified Excel Saving Function ---
def save_dfs_to_excel(list_of_dfs, sheet_names, header_infos, file_name="output.xlsx"):
    """Saves DataFrames to Excel, with a descriptive header inside each sheet."""
    if not all(len(lst) == len(list_of_dfs) for lst in [sheet_names, header_infos]):
        raise ValueError("The number of DataFrames, sheet names, and header infos must be the same.")
    try:
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            for i, df in enumerate(list_of_dfs):
                sheet_name = sheet_names[i]
                df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
                # Add header inside the sheet
                worksheet = writer.sheets[sheet_name]
                worksheet.cell(row=1, column=1, value=header_infos[i])
        print(f"\nSuccessfully saved data to '{os.path.abspath(file_name)}'")
    except Exception as e:
        print(f"An error occurred while saving to Excel: {e}")

# --- Data Loading (No changes) ---
def load_data(source_type, csv_path=None, table_name=None, connection=None):
    if source_type == 'csv':
        df = pd.read_csv(csv_path, sep=',')
    elif source_type == 'sql':
        query = f"SELECT * FROM {table_name};"
        df = pd.read_sql_query(query, connection)
    else:
        raise ValueError("Invalid source_type. Choose 'csv' or 'sql'.")
    return df

def load_and_preprocess_data(source_type, csv_file, table_name, appr_amount_col, appr_txns_col):
    cnxn = None; source = csv_file
    if source_type == 'sql':
        source = table_name
        cnxn = pypyodbc.connect(DSN="IMPALA64-Prod", Schema="core", autocommit=True)
    
    df_raw = load_data(source_type=source_type, csv_path=source, table_name=source, connection=cnxn)
    
    df_raw = df_raw.rename(columns={
        "total_amount": "txn_amt", "total_txns": "txn_cnt",
        appr_amount_col: "app_amt", appr_txns_col: "app_cnt",
        "declined_amount": "dcl_amt", "declined_txns": "dcl_cnt",
        "qt_fraud": "fraud_cnt", "amount_fraud": "fraud_amt",
    })

    if 'fraud_cnt' not in df_raw.columns:
        print(">> WARNING: 'qt_fraud' column not found in source. Creating dummy fraud count data.")
        df_raw['fraud_cnt'] = 1
    if 'fraud_amt' not in df_raw.columns:
        print(">> WARNING: 'amount_fraud' column not found in source. Creating dummy fraud amount data.")
        df_raw['fraud_amt'] = 1

    if cnxn: cnxn.close()
    return df_raw

if __name__ == "__main__":
    # Load presets for help text
    def get_presets_help():
        try:
            with open('presets.json', 'r') as f:
                presets = json.load(f)['presets']
                help_text = "\nPRESETS:\n"
                for name, config in presets.items():
                    help_text += f"  {name}: {config['participants']} participants, {config['max_percent']}% max, combinations {config['combinations']}\n"
                return help_text
        except:
            return """
PRESETS:
  conservative: 6 participants, 25% max, combinations [1,2,3]
  standard:    4 participants, 35% max, combinations [5,1,2]  
  aggressive:  7 participants, 40% max, combinations [1,2,3,4,5]
            """

    parser = argparse.ArgumentParser(
        description='Benchmark Analysis Tool - Compare issuer performance against peer groups',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
EXAMPLES:
  # Quick rate analysis with defaults
  python benchmark_tool.py rate --csv data.csv --issuer "BANCO SANTANDER" --break month_year

  # Share analysis for wallet flag
  python benchmark_tool.py share --csv data.csv --issuer "BANCO SANTANDER" --break wallet_flag

  # Multiple breaks with custom settings
  python benchmark_tool.py rate --csv data.csv --issuer "BANCO SANTANDER" \\
    --break month_year industry wallet_flag \\
    --participants 6 --max-percent 30

  # Use preset configurations
  python benchmark_tool.py rate --csv data.csv --issuer "BANCO SANTANDER" \\
    --break month_year --preset conservative

  # List available presets
  python benchmark_tool.py presets

{get_presets_help()}
        """
    )
    
    # Create subparsers for different analysis types
    subparsers = parser.add_subparsers(dest='command', help='Analysis type')
    
    # Get available preset names for argument choices
    def get_preset_choices():
        try:
            with open('presets.json', 'r') as f:
                presets = json.load(f)['presets']
                return list(presets.keys())
        except:
            return ['conservative', 'standard', 'aggressive']
    
    preset_choices = get_preset_choices()
    
    # Rate analysis subcommand
    rate_parser = subparsers.add_parser('rate', help='Rate-based benchmark analysis (approval rates, fraud rates)')
    rate_parser.add_argument('--csv', required=True, help='Path to CSV file')
    rate_parser.add_argument('--issuer', required=True, help='Name of the client issuer')
    rate_parser.add_argument('--break', dest='breaks', nargs='+', required=True, 
                           help='Break columns to analyze (e.g., month_year industry)')
    rate_parser.add_argument('--issuer-col', default='issuer_name', help='Issuer column name (default: issuer_name)')
    rate_parser.add_argument('--participants', type=int, default=4, help='Number of participants (default: 4)')
    rate_parser.add_argument('--max-percent', type=float, default=35, help='Max percentage per peer (default: 35)')
    rate_parser.add_argument('--combinations', nargs='+', type=int, default=[5,1,2], 
                           help='Combination priority order (default: 5 1 2)')
    rate_parser.add_argument('--preset', choices=preset_choices, 
                           help='Use preset configuration')
    
    # Share analysis subcommand  
    share_parser = subparsers.add_parser('share', help='Share-based benchmark analysis (market share, distribution)')
    share_parser.add_argument('--csv', required=True, help='Path to CSV file')
    share_parser.add_argument('--issuer', required=True, help='Name of the client issuer')
    share_parser.add_argument('--break', dest='breaks', nargs='+', required=True,
                           help='Break columns to analyze (e.g., wallet_flag industry)')
    share_parser.add_argument('--issuer-col', default='issuer_name', help='Issuer column name (default: issuer_name)')
    share_parser.add_argument('--participants', type=int, default=4, help='Number of participants (default: 4)')
    share_parser.add_argument('--max-percent', type=float, default=35, help='Max percentage per peer (default: 35)')
    share_parser.add_argument('--combinations', nargs='+', type=int, default=[5,1,2],
                           help='Combination priority order (default: 5 1 2)')
    share_parser.add_argument('--preset', choices=preset_choices,
                           help='Use preset configuration')
    
    # Presets subcommand
    presets_parser = subparsers.add_parser('presets', help='List available preset configurations')
    
    # Legacy compatibility subcommand
    legacy_parser = subparsers.add_parser('legacy', help='Legacy command-line interface for backward compatibility')
    legacy_parser.add_argument('--type', choices=['csv', 'sql'], required=True, help='Data source type')
    legacy_parser.add_argument('--csv-file', dest='csv_file', help='Path to CSV file')
    legacy_parser.add_argument('--table-name', dest='table_name', help='SQL table name')
    legacy_parser.add_argument('--appr-amount-col', default='appr_amount', help='Approved amount column')
    legacy_parser.add_argument('--appr-txns-col', default='appr_txns', help='Approved transactions column')
    legacy_parser.add_argument('--break-def', action='append', required=True, help='Break definition')
    legacy_parser.add_argument('--comb-priority', nargs='+', type=int, default=[1,2,3,4,5], help='Combination priority')
    legacy_parser.add_argument('--metric-type', action='append', help='Metric type definition')
    legacy_parser.add_argument('--issuer-column', default='issuer_name', help='Issuer column name')
    legacy_parser.add_argument('--issuer-name', default='BANCO SANTANDER (BRASIL) S.A.', help='Issuer name')
    legacy_parser.add_argument('--num-participants', type=int, default=4, help='Number of participants')
    legacy_parser.add_argument('--max-percentage', type=float, default=35, help='Maximum percentage')
    legacy_parser.add_argument('--num-combinations', type=int, default=5, help='Number of combinations')
    
    args = parser.parse_args()

    # Handle presets
    def load_presets():
        """Load presets from JSON file, fallback to defaults if file not found"""
        try:
            with open('presets.json', 'r') as f:
                return json.load(f)['presets']
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # Fallback to hardcoded presets
            return {
                "conservative": {
                    "description": "High privacy requirements, regulatory compliance",
                    "participants": 6,
                    "max_percent": 25,
                    "combinations": [1, 2, 3]
                },
                "standard": {
                    "description": "Most common use cases, good balance", 
                    "participants": 4,
                    "max_percent": 35,
                    "combinations": [5, 1, 2]
                },
                "aggressive": {
                    "description": "Limited data availability, need more flexibility",
                    "participants": 7,
                    "max_percent": 40,
                    "combinations": [1, 2, 3, 4, 5]
                }
            }
    
    def apply_preset(preset_name, args):
        presets = load_presets()
        if preset_name in presets:
            preset = presets[preset_name]
            args.participants = preset['participants']
            args.max_percent = preset['max_percent']
            args.combinations = preset['combinations']
            print(f"Applied preset '{preset_name}': {preset['description']}")
        else:
            print(f"Warning: Preset '{preset_name}' not found. Using default settings.")
    
    # --- Helper functions (defined before use) ---
    def parse_metric_type_args(metric_type_args):
        metric_type_map = {}
        if metric_type_args:
            for entry in metric_type_args:
                if ':' in entry:
                    var, mtype = entry.split(':', 1)
                    metric_type_map[var.strip()] = mtype.strip().lower()
        return metric_type_map

    def get_metric_type_for_break(break_name, metric_type_map):
        # Try exact match, else default to 'rate'
        return metric_type_map.get(break_name, 'rate')

    # Process arguments based on command
    if args.command == 'presets':
        # List available presets
        presets = load_presets()
        print("Available Preset Configurations:")
        print("=" * 50)
        for name, config in presets.items():
            print(f"\n{name.upper()}:")
            print(f"  Description: {config['description']}")
            print(f"  Participants: {config['participants']}")
            print(f"  Max Percentage: {config['max_percent']}%")
            print(f"  Combinations: {config['combinations']}")
        print(f"\nTo use a preset: --preset <name>")
        print(f"To add new presets: Edit presets.json file")
        exit(0)
        
    elif args.command == 'legacy':
        # Legacy mode - use existing logic
        metric_type_map = parse_metric_type_args(getattr(args, 'metric_type', None))
        # ... rest of legacy logic
        pass
        
    elif args.command in ['rate', 'share']:
        # New simplified mode
        if args.preset:
            apply_preset(args.preset, args)
        
        # Convert new args to legacy format for compatibility
        legacy_args = argparse.Namespace()
        legacy_args.type = 'csv'
        legacy_args.csv_file = args.csv
        legacy_args.table_name = None
        legacy_args.appr_amount_col = 'appr_amount'
        legacy_args.appr_txns_col = 'appr_txns'
        legacy_args.break_def = args.breaks
        legacy_args.comb_priority = args.combinations
        legacy_args.issuer_column = args.issuer_col
        legacy_args.issuer_name = args.issuer
        legacy_args.num_participants = args.participants
        legacy_args.max_percentage = args.max_percent
        legacy_args.num_combinations = 5
        # Set metric type based on command
        if args.command == 'share':
            legacy_args.metric_type = [f"Break_by_{break_name}:share" for break_name in args.breaks]
            legacy_args.command = 'share'
        else:
            legacy_args.metric_type = None
            legacy_args.command = 'rate'
        args = legacy_args
        metric_type_map = parse_metric_type_args(getattr(args, 'metric_type', None))
        
    else:
        parser.print_help()
        exit(1)

    def get_metric_type_for_break(break_name, metric_type_map):
        # Try exact match, else default to 'rate'
        return metric_type_map.get(break_name, 'rate')

    # --- Share metric aggregation and KPI logic ---
    def aggregate_share_metric(df, issuer_column, cat_col):
        df_cat = df.groupby([issuer_column, cat_col]).size().reset_index(name='count')
        df_cat['total'] = df_cat.groupby(issuer_column)['count'].transform('sum')
        df_cat['share'] = df_cat['count'] / df_cat['total']
        df_pivot = df_cat.pivot(index=issuer_column, columns=cat_col, values='share').reset_index().fillna(0)
        return df_pivot

    def kpis_for_share_metric(df_pivot, issuer_column, issuer_name):
        vars_to_eval = [col for col in df_pivot.columns if col != issuer_column]
        df_kpis = pd.DataFrame(columns=['Metric', 'Peer Group Average Share'])
        player_row = df_pivot[df_pivot[issuer_column] == issuer_name]
        if player_row.empty:
            return df_kpis
        for var in vars_to_eval:
            # Calculate average share for peer group (excluding the client)
            peer_shares = df_pivot[(df_pivot[issuer_column] != issuer_name)][var]
            avg_share = peer_shares.mean()
            series_to_append = pd.Series([var, round(avg_share, 4)], index=df_kpis.columns)
            df_kpis = pd.concat([df_kpis, series_to_append.to_frame().T], ignore_index=True)
        return df_kpis

    def run_share_benchmark(df_to_process, break_cols, issuer_column, issuer_name, comb_priority_list, rules, num_combinations, num_participants, max_percentage):
        cat_col = break_cols[0]
        df_pivot = aggregate_share_metric(df_to_process, issuer_column, cat_col)
        # Rename issuer column to 'Issuer Name' for compatibility
        df_pivot = df_pivot.rename(columns={issuer_column: 'Issuer Name'})
        columns_pivot_share = [col for col in df_pivot.columns if col != 'Issuer Name']
        dict2convert_share = {cat: cat for cat in columns_pivot_share}
        initial_df = df_pivot.copy()
        initial_df.columns = initial_df.columns.str.strip()
        vars_to_eval = columns_pivot_share  # Use all category columns at once for group validation
        tuple_final = get_combinations_proposed(
            initial_df, num_participants, max_percentage, num_combinations, vars_to_eval, rules, 'Issuer Name'
        )
        peer_group_names = []
        if tuple_final:
            first_valid_result = next((tup for tup in tuple_final if tup[1]), None)
            if first_valid_result:
                try:
                    selected_df = first_valid_result[1][comb_priority_list[0] - 1]
                    peer_group_names = selected_df['Issuer Name'].tolist()
                except IndexError:
                    print(f"Warning: Combination {comb_priority_list[0]} not found for this break.")
        df_kpis = kpis_for_share_metric(df_pivot, 'Issuer Name', issuer_name)
        return df_kpis, peer_group_names, comb_priority_list[0] if peer_group_names else None

    # --- Setup Logging ---
    log_filename = f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    setup_logging(log_filename, args)

    # --- Configuration ---
    df_geral = load_and_preprocess_data(args.type, args.csv_file, args.table_name, args.appr_amount_col, args.appr_txns_col)
    target_breaks = generate_target_breaks(args.break_def, df_geral, args.comb_priority)
    rows = ['issuer_name']; columns_pivot = ["app", "txn", "fraud"]
    dict2convert = {"Approved": "app", "Total": "txn", "Fraud": "fraud"}
    issuer_column = args.issuer_column
    issuer_name = args.issuer_name
    rules = [(5, 26), (6, 31), (7, 36), (10, 41)]
    num_participants = args.num_participants
    max_percentage = args.max_percentage
    num_combinations = args.num_combinations
    
    # --- Main Execution Loop ---
    kpi_results = {}
    print("Starting benchmark analysis...")
    for name, params in target_breaks.items():
        break_cols, df_to_process, comb_priority_list = params
        metric_type = get_metric_type_for_break(name, metric_type_map)
        if metric_type == 'share':
            df_kpis_result, peer_group_result, successful_comb = run_share_benchmark(
                df_to_process, break_cols, issuer_column, issuer_name, comb_priority_list, rules, num_combinations, num_participants, max_percentage
            )
        else:
            df_kpis_result, peer_group_result, successful_comb = run_analysis_with_fallback(
                comb_priority_list, df_to_process, rows, break_cols, columns_pivot, dict2convert,
                issuer_column, issuer_name, rules, num_combinations, num_participants, max_percentage
            )
        kpi_results[name] = (df_kpis_result, peer_group_result, successful_comb)
        log_result(log_filename, name, df_to_process.shape, kpi_results[name])
    
    # --- Prepare for Excel Export ---
    header_info_list = []
    for name, result in kpi_results.items():
        df, peer_group, comb = result
        if comb:
            header = f"Analysis for: {name} | Status: SUCCESS | Combination Used: #{comb} | Peers: {peer_group}"
        else:
            header = f"Analysis for: {name} | Status: FAILED - No valid peer combination found."
        header_info_list.append(header)
        
    # Determine analysis type for filename suffix
    analysis_type = "unknown"
    if args.command == 'share':
        analysis_type = "share"
    elif args.command == 'rate':
        analysis_type = "rate"
    elif args.command == 'legacy':
        # Try to determine from metric types
        if hasattr(args, 'metric_type') and args.metric_type:
            if any('share' in mt for mt in args.metric_type):
                analysis_type = "share"
            else:
                analysis_type = "rate"
        else:
            analysis_type = "rate"  # Default for legacy
    
    save_dfs_to_excel(
        list_of_dfs=[result[0] for result in kpi_results.values()],
        sheet_names=[f"Break_{i+1}" for i in range(len(kpi_results))],
        header_infos=header_info_list,
        file_name=f"benchmark_output_{datetime.now().strftime('%Y%m%d')}_{analysis_type}.xlsx"
    )
    print(f"\nLog file created: {log_filename}")