# CityFinder
# Simple recommendation algorithm

import math
import random
import numpy as np
import pandas as pd
import City as city
from .models import *

WEIGHT_DECAY = .15
SPECIAL_CRITERIA = ['weather', 'community']
CALCULATED_SCORES = ['safe', 'lgbtq', 'hisp', 'weather', 'community']
RELATION_DICT = { 
'cost': [COL, 'total_index'], 
'safe':[Crime, 'bulglary'], 
'community': {'hispanic': [Hisp, 'hisp_count'], 
 'lgbtq': [LGBT, 'Male_Male_HH', 'Female_Female_HH', 'Total_HH'],
 'young': [Age, 'median_age'], 
 'old': [Age, 'old_age_depend_ratio']},
'rent': [Rent, 'bed_1_med_price'], 
'transit': [Walk, 'transit_score'], 
'walk': [Walk, 'walk_score'],  
'bike': [Walk, 'bike_score'], 
'weather': {'sun': [Weather, 'avg_annual_precip_in_days'], 
 'temp': [Weather, 'avg_temp_jan'],
 'seasons' : [Weather, 'avg_temp_jan', 'avg_temp_april', 
    'avg_temp_july', 'avg_temp_oct']},
'cities' : [City, 'city', 'state'], 
'size': [Walk, 'population']}
CATEGORIES = {'seasons': ([0, 10, 20, float('inf')], [0, 1, 2]), 
              'sun': ([0, 75, 125, float('inf')], [0, 1, 2]),
              'temp': ([0, 40, 50, float('inf')], [2, 1, 0]), 
              'size': ([0, 299999, 999999, float('inf')],[0, 1, 2])}

def calculate_weights(n):
    '''
    Calculates a series of weights based of the number of inputted 
    preferences, n. N^2 time. 

    Input: n
    Output: a list of weights
    '''    
    rv = [100/n] * n
    for i in range(len(rv)):
        for j in range(i + 1, len(rv)):
            to_add = rv[j] * WEIGHT_DECAY
            rv[j] += -to_add
            rv[i] += to_add

    # Account for rounding error so that sum is 100
    if sum(rv) > 100: 
        sub = 100 - sum(rv)
        rv[-1] += sub     

    return sorted(rv, reverse = True)

def calculate_z_scores(array, i = None):
    '''
    Takes an array of values and computes a matching array with normalized 
    z-scores. Returns either the full array or, optionally, the z-score 
    matching a single entry, i, where i in the index in the array.

    Input: array of values
    Output: array or scores OR score for single index
    '''
    rv = []
    for j in range(len(array)): 
        if np.isnan(array[j]):
            array[j] = np.average(array[~np.isnan(array)])
    for x in array: 
        rv.append((x - np.average(array)) / np.std(array))
    if i != None: 
        return rv[i]
    else:
        return rv

def construct_dataframe(input_dict):
    '''
    Creates data dictionary with all necessary data.

    Input: input dictionary
    Output: 
     - pandas dataframe
     - priorities list (in order, highest to lowest)
     - communities list, if present
     - weather dictionary, if present
    '''
    data = {}
    priorities = input_dict['priorities']
    weather = {k:v for (k,v) in input_dict.items() if 'pr' not in k}
    if 'size' in weather:
        size = weather.pop('size')
    else: 
        size = None
    if 'communities' in weather:
        communities = weather.pop('communities')
    else:
        communities = None

    for criteria in priorities:
        if criteria not in SPECIAL_CRITERIA:
            criteria_info = RELATION_DICT[criteria]
            data[criteria] = get_data(criteria_info)
        elif criteria in SPECIAL_CRITERIA:
            for key in RELATION_DICT[criteria]:
                if criteria is 'weather':
                    criteria_info = RELATION_DICT[criteria][key]
                    data[key] = get_data(criteria_info)
                else: 
                    criteria_info = RELATION_DICT[criteria][key]
                    data[key] = get_data(criteria_info)                    

    data['size'] = get_data(RELATION_DICT['size'])
    data['cities'] = get_data(RELATION_DICT['cities'])
    
    rv = data['cities']
    rv.columns = ['city', 'city_id', 'state']

    for key in data:
        if key != 'cities':
            rv = pd.merge(rv, data[key], on='city_id')

    return (rv, priorities, communities, weather, size)

def get_data(criteria_info):
    '''
    Gets the city name and relevant column(s) for the criteria passed.

    Input: criteria name
    Output: pandas dataframe
    '''
    # For use in django:
    if criteria_info == RELATION_DICT['cities']:
        data = []
        for col in criteria_info[1:]:
            pull = criteria_info[0].objects.values('id', col)
            data.append(pull)
        rv = pd.DataFrame.from_records(data[0])
        for df in data[1:]:
            df = pd.DataFrame.from_records(df)
            rv = pd.merge(rv, df, on='id')

        return rv

    else:
        data = []
        for col in criteria_info[1:]:
            data.append(criteria_info[0].objects.values('city_id', col))
        rv = pd.DataFrame.from_records(data[0])
        for df in data[1:]:
            df = pd.DataFrame.from_records(df)
            rv = pd.merge(rv, df, on='city_id')

        return rv

def add_categorical_information(data, weather, priorities):
    '''
    Converts several columns into categorical information for filtering
    purposes.
    '''
    # Convert weather attributes to categorical data
    if 'weather' in priorities:
        for key in weather: 
            if key == 'seasons':
                cols = []
                concat = []
                for x in data.columns:
                    if 'avg_temp' in x: 
                        cols.append(x)
                if len(cols) > 4: 
                    cols.remove('avg_temp_jan_y')    
                for col in cols: 
                    concat.append(data[col])
                temps = pd.concat(concat, axis = 1)
                temps['temp_variation'] = temps.var(axis = 1)
                temps['temp_sd'] = temps['temp_variation'].apply(math.sqrt)
                temps['seasons'] = pd.cut(temps['temp_variation'], 
                    CATEGORIES[key][0], labels = CATEGORIES[key][1], 
                    right = True)
                temps = temps['seasons']
                data = pd.concat([data, temps], axis = 1)
            elif key == 'sun':
                data['sun'] = pd.cut(data['avg_annual_precip_in_days'],  
                 CATEGORIES[key][0], labels = CATEGORIES[key][1], right = True)
            elif key == 'temp':
                for x in data.columns: 
                    if 'avg_temp_jan' in x: 
                        col = x
                        break
                temp_level = pd.cut(data[col], CATEGORIES[key][0],
                  labels = CATEGORIES[key][1], right = True)
                temp_level.name = 'temp'
                data = pd.concat([data, temp_level], axis = 1)

    # Convert size to categorical data
    data['size'] = pd.cut(data['population'], CATEGORIES['size'][0], labels = 
        CATEGORIES['size'][1], right = True)

    return data

def calculate_rates(data, weather, communities, priorities):
    '''
    Calculates safety, hispanic, and lgbtq rates. Renames old, flips age 
    cardinality so that younger median age is a higher score.
    '''
    if 'safe' in priorities:
        data['safe'] = data['bulglary'] / (data['population'] / 1000)
    if 'hisp' in communities and 'community' in priorities:
        data['hisp'] = data['hisp_count'] / (data['population'] / 1000)
    if 'lgbtq' in communities and 'community' in priorities:
        data['lgbtq'] = (data['Female_Female_HH'] + data['Male_Male_HH']) / \
         (data['population'] / 1000)
    if 'old' in communities and 'community' in priorities:
        data['old'] = data['old_age_depend_ratio']
    if 'young' in communities and 'community' in priorities:
        data['young'] = ((-1 * pd.DataFrame(calculate_z_scores(data['median_age'] \
         ))) * np.std(data['median_age'])) + np.average(data['median_age'])
    
    if 'weather' in priorities:
        data = calculate_weather(data, weather)
    if len(communities) > 0 and 'community' in priorities:
        data = calculate_community(data, communities)

    return data

def calculate_weather(data, weather):
    '''
    Calculates weather agreement.
    '''
    count = 1
    cols = []
    for x in weather:
        col = 'weather_' + str(count)
        data[col] = (data[x] == int(weather[x]))
        data[col] = data[col].astype(int, copy = False)
        count += 1

    data['weather'] = pd.concat([data['weather_' + str(i)] for i in 
        range(1, count)], axis=1).sum(axis=1) / 3

    return data

def calculate_community(data, communities):
    '''
    Calculates community agreement.
    '''
    if communities[0] == '':
        return data
    count = 0
    for x in communities:
        count += 1
    if count > 1:
        data['community'] = pd.concat([data[x] for x in communities], axis = 1
            ).sum(axis=1) / count
    elif count == 1:
        data['community'] = data[communities[0]]
    return data

def add_criteria_scores(data, priorities, weather, size, communities):
    '''
    Creates City objects for each city and adds all criteria scores. 

    Input: list of cities, data dictionary
    Output: city_data list
    '''
    rv = []
    for row in data.iterrows():
        cit = city.City(row[1]['city'], row[1]['state'], row[1]['city_id'], 
            row[1]['size'])
        scores = {}
        index = data[data['city_id'] == [row[1]['city_id']]].index[0]
        for key in priorities:
            if key not in SPECIAL_CRITERIA and key not in CALCULATED_SCORES:
                if key is 'cost':
                    scores[key] = [calculate_z_scores(data[RELATION_DICT[key][1]],
                        index) * np.asarray(-1.0)]
                else:   
                    scores[key] = [calculate_z_scores(data[RELATION_DICT[key][1]],
                        index) * np.asarray(-1.0)] 
            elif key in CALCULATED_SCORES:
                if key == 'community' and communities[0] != '':
                    scores[key] = [calculate_z_scores(data[key], index)]
                elif key == 'community' and communities[0] == '':
                    scores[key] = [1]
        if 'safe' in priorities:
            scores['safe'] = [calculate_z_scores(data['safe'], index)] * np.asarray(-1.0)

        for key in scores:
            if str(scores[key]) == 'nan':
                scores[key] = [0]

        cit.all_scores = pd.DataFrame.from_dict(scores)

        if size != None:
            if cit.size == int(size):
                rv.append(cit)
        else: 
            rv.append(cit)

    return rv

def calculate_rank(city_data, weights, priorities):
    '''
    Calculates rank from a list of cities with scores.
    '''
    to_sort = []
    for entry in city_data:
        entry.calculate_score(weights, priorities)
        to_sort.append((entry.score, entry))
    to_sort = sorted(to_sort, reverse = True)

    city_data = []
    rank = 1
    for entry in to_sort: 
        entry[1].rank = rank
        city_data.append(entry[1])
        rank += 1
    return city_data

def make_scores_100(ranked_list):
    '''
    Converts the scores from the final ranked_list cities into a 
    scale of 0-100, for comprehension.
    '''
    scores_list = []
    for city in ranked_list:
        scores_list.append(city.score)

    scores = np.array(scores_list)
    if scores.min() < 0:
        max_score = scores.max() - scores.min()
        min_score = 0
    else:
        max_score = scores.max()
        min_score = scores.min()

    for i in range(len(scores_list)):
        if scores.min() < 0:
            ranked_list[i].score = 100 * ((scores_list[i] - scores.min()) / \
            (max_score - min_score))
        else:
            ranked_list[i].score = 100 * (scores_list[i] / \
            (max_score - min_score))

    return ranked_list

def run_calculations(input_dict):
    '''
    Carries out algorithm; returns cities dictionary. 

    Input: dictionary from django app
    Output: list of ranked cities, dictionary mapping city: city object, 
    '''
    data, priorities, communities, weather, size = construct_dataframe(input_dict)
    data = add_categorical_information(data, weather, priorities)
    data = calculate_rates(data, weather, communities, priorities)
    city_data = add_criteria_scores(data, priorities, weather, size, communities)
    weights = calculate_weights(len(priorities))
    ranked_list = calculate_rank(city_data, weights, priorities)    
    rv = make_scores_100(ranked_list)
    print("RETURNING RESULTS LIST, ", rv)

    if len(rv) > 10:
        rv = rv[:10]

    return rv



