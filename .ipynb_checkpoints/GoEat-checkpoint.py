#import modules
import numpy as np
import scipy
import pandas as pd
import math
import random
import sklearn
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.utils import shuffle
from scipy.sparse.linalg import svds
from itertools import combinations
import matplotlib.pyplot as plt
from nltk.corpus import stopwords

def users_interaction(interactions_df,num_interaction = 5):

    users_interactions_count_df = interactions_df.groupby(['userId', 'foodId']).size().groupby('userId').size()
    print('# users: %d' % len(users_interactions_count_df))
    users_with_enough_interactions_df = users_interactions_count_df[users_interactions_count_df >= num_interaction].reset_index()[['userId']]
    print('# users with at least ' + str(num_interaction) +'interactions: %d' % len(users_with_enough_interactions_df))

    return users_with_enougth_interactions_df

    print('# of interactions: %d' % len(interactions_df))
    interactions_from_selected_users_df = interactions_df.merge(users_with_enough_interactions_df,
               how = 'right',
               left_on = 'userId',
               right_on = 'userId')
    print('# of interactions from users with at least 5 interactions: %d' % len(interactions_from_selected_users_df))
    return interactions_from_selected_users_df

def smooth_user_preference(x):
    return math.log(1+x, 2)

def interaction_full(interactions_from_selected_users_df):
    interactions_full_df = interactions_from_selected_users_df \
                    .groupby(['userId', 'foodId'])['eventStrength'].mean() \
                    .apply(smooth_user_preference).reset_index()
    print('# of unique user/item interactions: %d' % len(interactions_full_df))

    return interactions_full_df


def get_items_interacted(person_id, interactions_df):
    # Get the user's data and merge in the movie information.
    interacted_items = interactions_df.loc[person_id]['foodId']
    return set(interacted_items if type(interacted_items) == pd.Series else [interacted_items])


#Top-N accuracy metrics consts

#EVAL_RANDOM_SAMPLE_NON_INTERACTED_ITEMS = 0

class ModelEvaluator:

    def set_random_sample_non_interacted(self,EVAL_RANDOM_SAMPLE_NON_INTERACTED_ITEMS):
        self.EVAL_RANDOM_SAMPLE_NON_INTERACTED_ITEMS = EVAL_RANDOM_SAMPLE_NON_INTERACTED_ITEMS


    def get_not_interacted_items_sample(self, person_id, sample_size, seed=42):
        interacted_items = get_items_interacted(person_id, interactions_full_indexed_df)
        all_items = set(food_df['foodId'])
        non_interacted_items = all_items - interacted_items

        random.seed(seed)
        non_interacted_items_sample = random.sample(non_interacted_items, sample_size)
        return set(non_interacted_items_sample)

    def _verify_hit_top_n(self, item_id, recommended_items, topn):
            try:
                index = next(i for i, c in enumerate(recommended_items) if c == item_id)
            except:
                index = -1
            hit = int(index in range(0, topn))
            return hit, index

    def evaluate_model_for_user(self, model, person_id):
        #Getting the items in test set
        interacted_values_testset = interactions_test_indexed_df.loc[person_id]
        if type(interacted_values_testset['foodId']) == pd.core.series.Series:
            person_interacted_items_testset = set(interacted_values_testset['foodId'])
        else:
            person_interacted_items_testset = set([int(interacted_values_testset['foodId'])])
        interacted_items_count_testset = len(person_interacted_items_testset)

        #Getting a ranked recommendation list from a model for a given user
        person_recs_df = model.recommend_items(person_id,
                                               items_to_ignore=get_items_interacted(person_id,
                                                                                    interactions_train_indexed_df),
                                               topn=10000000000)

        hits_at_5_count = 0
        hits_at_10_count = 0
        #For each item the user has interacted in test set
        for item_id in person_interacted_items_testset:
            #Getting a random sample (100) items the user has not interacted
            #(to represent items that are assumed to be no relevant to the user)
            non_interacted_items_sample = self.get_not_interacted_items_sample(person_id,
                                                                          sample_size=self.EVAL_RANDOM_SAMPLE_NON_INTERACTED_ITEMS,
                                                                          seed=item_id%(2**32)) ## seed=item_id%(2**32)
            #Combining the current interacted item with the 100 random items
            items_to_filter_recs = non_interacted_items_sample.union(set([item_id]))

            #Filtering only recommendations that are either the interacted item or from a random sample of 100 non-interacted items
            valid_recs_df = person_recs_df[person_recs_df['foodId'].isin(items_to_filter_recs)]
            valid_recs = valid_recs_df['foodId'].values
            #Verifying if the current interacted item is among the Top-N recommended items
            hit_at_5, index_at_5 = self._verify_hit_top_n(item_id, valid_recs, 5)
            hits_at_5_count += hit_at_5
            hit_at_10, index_at_10 = self._verify_hit_top_n(item_id, valid_recs, 10)
            hits_at_10_count += hit_at_10

        #Recall is the rate of the interacted items that are ranked among the Top-N recommended items,
        #when mixed with a set of non-relevant items
        recall_at_5 = hits_at_5_count / float(interacted_items_count_testset)
        recall_at_10 = hits_at_10_count / float(interacted_items_count_testset)

        person_metrics = {'hits@5_count':hits_at_5_count,
                          'hits@10_count':hits_at_10_count,
                          'interacted_count': interacted_items_count_testset,
                          'recall@5': recall_at_5,
                          'recall@10': recall_at_10}
        return person_metrics

    def evaluate_model(self, model):
        #print('Running evaluation for users')
        people_metrics = []
        for idx, person_id in enumerate(list(interactions_test_indexed_df.index.unique().values)):
            #if idx % 100 == 0 and idx > 0:
            #    print('%d users processed' % idx)
            person_metrics = self.evaluate_model_for_user(model, person_id)
            person_metrics['_person_id'] = person_id
            people_metrics.append(person_metrics)
        print('%d users processed' % idx)

        detailed_results_df = pd.DataFrame(people_metrics) \
                            .sort_values('interacted_count', ascending=False)

        global_recall_at_5 = detailed_results_df['hits@5_count'].sum() / float(detailed_results_df['interacted_count'].sum())
        global_recall_at_10 = detailed_results_df['hits@10_count'].sum() / float(detailed_results_df['interacted_count'].sum())

        global_metrics = {'modelName': model.get_model_name(),
                          'recall@5': global_recall_at_5,
                          'recall@10': global_recall_at_10}
        return global_metrics, detailed_results_df

class CFRecommender:

    MODEL_NAME = 'Collaborative Filtering'

    def __init__(self, cf_predictions_df, items_df=None):
        self.cf_predictions_df = cf_predictions_df
        self.items_df = items_df

    def get_model_name(self):
        return self.MODEL_NAME

    def recommend_items(self, user_id, items_to_ignore=[], topn=10, verbose=False):
        # Get and sort the user's predictions
        sorted_user_predictions = self.cf_predictions_df[user_id].sort_values(ascending=False) \
                                    .reset_index().rename(columns={user_id: 'recStrength'})

        # Recommend the highest predicted rating movies that the user hasn't seen yet.
        recommendations_df = sorted_user_predictions[~sorted_user_predictions['foodId'].isin(items_to_ignore)] \
                               .sort_values('recStrength', ascending = False) \
                               .head(topn)

        if verbose:
            if self.items_df is None:
                raise Exception('"items_df" is required in verbose mode')

            recommendations_df = recommendations_df.merge(self.items_df, how = 'left',
                                                          left_on = 'foodId',
                                                          right_on = 'foodId')[['recStrength', 'foodId', 'foodName']]


        return recommendations_df




def interactions_train_test_split(interactions_full_df, test_size=0.20):
    #randomise
    interactions_train_df, interactions_test_df = train_test_split(interactions_full_df,
                                   stratify=interactions_full_df['userId'],
                                   test_size=test_size)
    print('# interactions on Train set: %d' % len(interactions_train_df))
    print('# interactions on Test set: %d' % len(interactions_test_df))

    return interactions_train_df, interactions_test_df

#interactions_train_df, interactions_test_df = interactions_train_test_split(interactions_full_df, test_size=0.30)

def indexed_df(interactions_full_df,interactions_train_df,interactions_test_df):
    #Indexing by userId to speed up the searches during evaluation
    interactions_full_indexed_df = interactions_full_df.set_index('userId')
    interactions_train_indexed_df = interactions_train_df.set_index('userId')
    interactions_test_indexed_df = interactions_test_df.set_index('userId')

    return interactions_full_indexed_df, interactions_train_indexed_df, interactions_test_indexed_df

#interactions_full_indexed_df, interactions_train_indexed_df, interactions_test_indexed_df = indexed_df(interactions_full_df,interactions_train_df,interactions_test_df)

def users_items_svd(interactions_df, nfactors =15):
    #Creating a sparse pivot table with users in rows and items in columns
    users_items_pivot_matrix_df = interactions_df.pivot(index='userId',
                                                          columns='foodId',
                                                          values='eventStrength').fillna(0)

    users_items_pivot_matrix = users_items_pivot_matrix_df.values
    users_ids = list(users_items_pivot_matrix_df.index)

    #The number of factors to factor the user-item matrix.
    NUMBER_OF_FACTORS_MF = 15

    #Performs matrix factorization of the original user item matrix

    U, sigma, Vt = svds(users_items_pivot_matrix, k = NUMBER_OF_FACTORS_MF)

    sigma = np.diag(sigma)

    all_user_predicted_ratings = np.dot(np.dot(U, sigma), Vt)

    #Converting the reconstructed matrix back to a Pandas dataframe
    cf_preds_df = pd.DataFrame(all_user_predicted_ratings, columns = users_items_pivot_matrix_df.columns, index=users_ids).transpose()

    return cf_preds_df

#cf_preds_df = users_items_svd(interactions_train_df, nfactors =15)

def item_recommenation(model, food_df):
    personNum = int(input('userId를 입력해주세요 : '))
    rec_model = model.recommend_items(personNum,verbose=True)
    for food in range(len(food_df.foodId)):
        rec_model.loc[rec_model.foodId == food_df.foodId[food],'foodName'] = food_df.foodName[food]
        rec_model.index = range(1,len(rec_model)+1)

    return rec_model

class ContentBasedRecommender:

    MODEL_NAME = 'Content-Based'

    def __init__(self, items_df=None,item_ids=None):
        self.item_ids = item_ids
        self.items_df = items_df

    def get_model_name(self):
        return self.MODEL_NAME

    def _get_similar_items_to_user_profile(self, person_id, topn=1000):
        #Computes the cosine similarity between the user profile and all item profiles
        cosine_similarities = cosine_similarity(user_profiles[person_id], tfidf_matrix)
        #Gets the top similar items
        similar_indices = cosine_similarities.argsort().flatten()[-topn:]
        #Sort the similar items by similarity
        similar_items = sorted([(item_ids[i], cosine_similarities[0,i]) for i in similar_indices], key=lambda x: -x[1])
        return similar_items

    def recommend_items(self, user_id, items_to_ignore=[], topn=10, verbose=False):
        similar_items = self._get_similar_items_to_user_profile(user_id)
        #Ignores items the user has already interacted
        similar_items_filtered = list(filter(lambda x: x[0] not in items_to_ignore, similar_items))

        recommendations_df = pd.DataFrame(similar_items_filtered, columns=['foodId', 'recStrength']) \
                                    .head(topn)

        if verbose:
            if self.items_df is None:
                raise Exception('"items_df" is required in verbose mode')

            recommendations_df = recommendations_df.merge(self.items_df, how = 'left',
                                                          left_on = 'foodId',
                                                          right_on = 'foodId')[['recStrength', 'foodId', 'foodName']]


        return recommendations_df
def tfidf_vectorizer(food_df,column_name,stopwords_list ):
    stopwords_list = stopwords_list
    vectorizer = TfidfVectorizer(analyzer='word',
                     ngram_range=(1, 2),
                     min_df=0.003,
                     max_df=0.5,
                     max_features=5000,
                     stop_words=stopwords_list)
    item_ids = food_df['foodId'].tolist()

    tfidf_matrix = vectorizer.fit_transform(food_df[column_name])
    #foodName, foodDescribtion!!!
    tfidf_feature_names = vectorizer.get_feature_names()

    return tfidf_matrix, tfidf_feature_names


def get_item_profile(item_ids):
    idx = item_ids.index(item_id)
    item_profile = tfidf_matrix[idx:idx+1]
    return item_profile

def get_item_profiles(ids):
    item_profiles_list = [get_item_profile(x) for x in ids]
    item_profiles = scipy.sparse.vstack(item_profiles_list)
    return item_profiles

def build_users_profile(person_id, interactions_indexed_df):
    interactions_person_df = interactions_indexed_df.loc[person_id]
    user_item_profiles = get_item_profiles(interactions_person_df['foodId'])

    user_item_strengths = np.array(interactions_person_df['eventStrength']).reshape(-1,1)
    #Weighted average of item profiles by the interactions strength
    user_item_strengths_weighted_avg = np.sum(user_item_profiles.multiply(user_item_strengths), axis=0) / np.sum(user_item_strengths)
    user_profile_norm = sklearn.preprocessing.normalize(user_item_strengths_weighted_avg)
    return user_profile_norm

def build_users_profiles(interactions_full_df,food_df):
    interactions_indexed_df = interactions_full_df[interactions_full_df['foodId'] \
                                                   .isin(food_df['foodId'])].set_index('userId')
    user_profiles = {}
    for person_id in interactions_indexed_df.index.unique():
        user_profiles[person_id] = build_users_profile(person_id, interactions_indexed_df)
    return user_profiles


def joint_recommender_model(recommender_model, *args):

    model = recommender_model

    model_list=[]
    userId_list=[]

   #find the first common food shared by people searching from top 1 to the last.

    top=1
    common_content = []
    while common_content == []:

        userId_list = []
        model_list = []
        user1_content=[]
        common_content = []


        for arg in args :

            userId_list.append(arg)
            model_list.append(model.recommend_items(arg,verbose=True,topn=top))

        user1_content = list(model_list[0].foodId)
        common_content = user1_content

        for user in model_list:
            user_content = list(user.foodId)
            common_content = list(set(common_content).intersection(user_content))


        if common_content == []:
            top=top+1
        else:
            break



    joint_content_df = food_df[food_df.foodId == common_content]

    print(len(userId_list),'명이 함께 먹을 추천 음식은 [',list(joint_content_df.foodName)[0],']입니다!!!\n')

    person = 0

    for user in model_list:
        rank = user[user.foodId == common_content].index[0] + 1

        print('UserId ', userId_list[person],'번은 이 음식을', rank, '번 째로 좋아합니다!')

        person = person + 1



#Add new interaction
def new_interaction(old_interaction_df, userId, foodId, eventStrength):
    new_interaction_df = pd.DataFrame([[userId,foodId,eventStrength]],columns = ['userId','foodId','eventStrength'])
    old_interaction_df = old_interaction_df.append(new_interaction_df,ignore_index=True)
    return old_interaction_df

#Add new food
def new_food(old_food_df,foodId,foodName):
    new_food_df = pd.DataFrame([[foodId,foodName]], columns = ['foodId','foodName'])
    old_food_df = old_food_df.append(new_food_df,ignore_index=True)
    return old_food_df


#Add new users
def new_user_info(old_user_info_df, userId,timestamp,userName,sex,age,aloneHow,eatAlone,eatDate,eatTogether):
    new_user_info_df = pd.DataFrame([[userId,timestamp,userName,sex,age,aloneHow,eatAlone,eatDate,eatTogether]],
                                    columns = ['userId','timestamp','userName','sex','age','aloneHow','eatAlone','eatDate','eatTogether'])
    old_user_info_df = old_user_info_df.append(new_user_info_df,ignore_index=True)

def cold_start_question(userId,number):
    foodIdlist = food_df.foodId.tolist()
    selected_content = np.random.choice(foodIdlist,number,replace=False )

    question = []

    for foodId in selected_content:
        food = food_df.foodName[food_df.foodId == foodId].to_string(header=False,index=False)
        eventStrength = ''

        while eventStrength not in ['0','1','2','3','4','5']:
            eventStrength = input('\n당신은 ' + food+'을(를) 얼마나 좋아하십니까?\n\n0 - 먹어본 적 없음\n1 - 별로 좋아하지 않음\n5 - 매우 좋아함\n\n')

            if eventStrength not in ['0','1','2','3','4','5']:
                print('\n\n0-5 사이의 숫자릅 입력하여 주세요!')

        eventStrength = int(eventStrength)

        question.append([userId,foodId,eventStrength])

    starting_question_df = pd.DataFrame(question,columns = ['userId','foodId','eventStrength'])

    return starting_question_df
