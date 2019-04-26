import numpy as np
import pandas as pd

import statsmodels.api as sm
from statsmodels.tsa.stattools import coint, adfuller

from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn import preprocessing
from sklearn.metrics import silhouette_score

# just set the seed for the random number generator
np.random.seed(107)


class SeriesAnalyser:
    """
    This class contains a set of functions to deal with time series analysis.
    """

    def __init__(self):
        """
        :initial elements
        """

    def check_for_stationarity(self, X, cutoff=0.01):
        """
        Receives as input a time series and a cutoff value.
        H_0 in adfuller is unit root exists (non-stationary).
        We must observe significant p-value to convince ourselves that the series is stationary.
        """

        result = adfuller(X)
        # result contains:
        # 0: t-statistic
        # 1: p-value
        # others: please see https://www.statsmodels.org/dev/generated/statsmodels.tsa.stattools.adfuller.html

        return {'t_statistic': result[0], 'p_value': result[1], 'critical_values': result[4]}

    def check_for_cointegration(self, train_series, test_series):
        """
        Gets two time series as inputs and provides information concerning cointegration stasttics
        Y - b*X : Y is dependent, X is independent
        """

        # for some reason is not giving right results
        # t_statistic, p_value, crit_value = coint(X,Y, method='aeg')

        # perform test manally in both directions
        X = train_series[0]
        Y = train_series[1]
        pairs = [(X, Y), (Y, X)]
        coint_stats = [0] * 2

        for i, pair in enumerate(pairs):
            S1 = pair[0]
            S2 = pair[1]

            series_name = S1.name
            S1 = sm.add_constant(S1)
            # Y = bX + c
            # ols: (Y, X)
            results = sm.OLS(S2, S1).fit()
            S1 = S1[series_name]
            b = results.params[S1.name]

            spread = S2 - b * S1
            stats = self.check_for_stationarity(pd.Series(spread, name='Spread'))
            zero_cross = self.zero_crossings(spread)
            hl = self.calculate_half_life(spread)
            hurst_exponent = self.hurst(spread)
            coint_stats[i] = {'t_statistic': stats['t_statistic'],
                              'critical_val': stats['critical_values'],
                              'p_value': stats['p_value'],
                              'coint_coef': b,
                              'zero_cross': zero_cross,
                              'half_life': int(round(hl)),
                              'hurst_exponent': hurst_exponent,
                              'spread': spread,
                              'Y_train': S2,
                              'X_train': S1
                              }

        # select lowest t-statistic as representative test
        if abs(coint_stats[0]['t_statistic']) > abs(coint_stats[1]['t_statistic']):
            coint_result = coint_stats[0]
            coint_result['X_test'] = test_series[0]
            coint_result['Y_test'] = test_series[1]

        else:
            coint_result = coint_stats[1]
            coint_result['X_test'] = test_series[1]
            coint_result['Y_test'] = test_series[0]

        return coint_result

    def find_pairs(self, data_train, data_test, p_value_threshold, min_half_life=5, min_zero_crossings=0,
                   hurst_threshold=0.5):
        """
        This function receives a df with the different securities as columns, and aims to find tradable
        pairs within this world. There is a df containing the training data and another one containing test data
        Tradable pairs are those that verify:
            - cointegration
            - minimium half life
            - minimium zero crossings

        :param data_train: df with training prices in columns
        :param data_test: df with testing prices in columns
        :param p_value_threshold:  pvalue threshold for a pair to be cointegrated
        :param min_half_life: minimium half life value of the spread to consider the pair
        :param min_zero_crossings: minimium number of allowed zero crossings
        :param hurst_threshold: mimimium acceptable number for hurst threshold
        :return: pairs that passed test
        """
        n = data_train.shape[1]
        keys = data_train.keys()
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                S1_train = data_train[keys[i]]; S2_train = data_train[keys[j]]
                S1_test = data_test[keys[i]]; S2_test = data_test[keys[j]]
                result = self.check_for_cointegration((S1_train, S2_train), (S1_test, S2_test))
                pvalue = result['p_value']
                if pvalue < p_value_threshold: # verifies required pvalue
                    hl = self.calculate_half_life(result['spread'])
                    if hl >= min_half_life: # verifies required half life
                        if result['zero_cross'] >= min_zero_crossings: # verifies required zero crossings
                            if result['hurst_exponent'] < hurst_threshold: # verifies hurst exponent
                                pairs.append((keys[i], keys[j], result))

        return pairs

    def pairs_overlap(self, pairs, p_value_threshold, min_zero_crossings, min_half_life, hurst_threshold):
        """
        This function receives the pairs identified in the training set, and returns a list of the pairs
        which are still cointegrated in the test set.

        :param pairs: list of pairs in the train set for which to verify cointegration in the test set
        :param p_value_threshold: p_value to consider cointegration
        :param min_zero_crossings: zero crossings to consider cointegration
        :param min_half_life: minimum half-life to consider cointegration
        :param hurst_threshold:  maximum threshold to consider cointegration

        :return: list with pairs overlapped
        :return: list with indices from the pairs overlapped
        """
        pairs_overlapped = []
        pairs_overlapped_index = []

        for index, pair in enumerate(pairs):
            # get consituents
            X = pair[2]['X_test']
            Y = pair[2]['Y_test']
            # check if pairs is valid
            series_name = X.name
            X = sm.add_constant(X)
            results = sm.OLS(Y, X).fit()
            X = X[series_name]
            b = results.params[X.name]
            spread = Y - b * X
            stats = self.check_for_stationarity(pd.Series(spread, name='Spread'))

            if stats['p_value'] < p_value_threshold:  # verifies required pvalue
                hl = self.calculate_half_life(spread)
                if hl >= min_half_life:  # verifies required half life
                    zero_cross = self.zero_crossings(spread)
                    if zero_cross >= min_zero_crossings:  # verifies required zero crossings
                        hurst_exponent = self.hurst(spread)
                        if hurst_exponent < hurst_threshold:  # verifies hurst exponent
                            pairs_overlapped.append(pair)
                            pairs_overlapped_index.append(index)

        return pairs_overlapped, pairs_overlapped_index

    def zscore(self, series):
        """
        Returns the nromalized time series assuming a normal distribution
        """
        return (series - series.mean()) / np.std(series)

    def calculate_half_life(self, z_array):
        """
        This function calculates the half life parameter of a
        mean reversion series
        """
        z_lag = np.roll(z_array, 1)
        z_lag[0] = 0
        z_ret = z_array - z_lag
        z_ret[0] = 0

        # adds intercept terms to X variable for regression
        z_lag2 = sm.add_constant(z_lag)

        model = sm.OLS(z_ret[1:], z_lag2[1:])
        res = model.fit()

        halflife = -np.log(2) / res.params[1]

        # print(res.params)
        # print('\nEstimated lambda:',res.params[1])
        # print('Estimated miu:', res.params[0])
        # print('Estimated half-life:', halflife)

        return halflife

    def hurst(self, ts):
        """
        Returns the Hurst Exponent of the time series vector ts.
        Series vector ts should be a price series.
        Source: https://www.quantstart.com/articles/Basics-of-Statistical-Mean-Reversion-Testing"""
        # Create the range of lag values
        lags = range(2, 100)

        # Calculate the array of the variances of the lagged differences
        # Here it calculates the variances, but why it uses
        # standard deviation and then make a root of it?
        tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]

        # Use a linear fit to estimate the Hurst Exponent
        poly = np.polyfit(np.log(lags), np.log(tau), 1)

        # Return the Hurst exponent from the polyfit output
        return poly[0] * 2.0

    def variance_ratio(self, ts, lag=2):
        """
        Returns the variance ratio test result
        Source: https://gist.github.com/jcorrius/56b4983ca059e69f2d2df38a3a05e225#file-variance_ratio-py
        """
        # make sure we are working with an array, convert if necessary
        ts = np.asarray(ts)

        # Apply the formula to calculate the test
        n = len(ts)
        mu = sum(ts[1:n] - ts[:n - 1]) / n
        m = (n - lag + 1) * (1 - lag / n)
        b = sum(np.square(ts[1:n] - ts[:n - 1] - mu)) / (n - 1)
        t = sum(np.square(ts[lag:n] - ts[:n - lag] - lag * mu)) / m
        return t / (lag * b)

    def zero_crossings(self, x):
        """
        Function that counts the number of zero crossings of a given signal
        :param x: the signal to be analyzed
        """
        x = x - x.mean()
        zero_crossings = sum(1 for i, _ in enumerate(x) if (i + 1 < len(x)) if ((x[i] * x[i + 1] < 0) or (x[i] == 0)))

        return zero_crossings

    def apply_PCA(self, n_components, df, svd_solver='auto'):
        """
        This function applies Principal Component Analysis to the df given as
        parameter

        :param n_components: number of principal components
        :param df: dataframe containing time series for analysis
        :param svd_solver: solver for PCA: see PCA documentation
        :return: reduced normalized and transposed df
        """

        if not isinstance(n_components, str):
            if n_components > df.shape[1]:
                print("ERROR: number of components larger than samples...")
                exit()

        pca = PCA(n_components=n_components, svd_solver=svd_solver)
        pca.fit(df)
        explained_variance = pca.explained_variance_

        # standardize
        X = preprocessing.StandardScaler().fit_transform(pca.components_.T)
        #print('New shape: ', X.shape)

        return X, explained_variance

    def apply_DBSCAN(self, eps, min_samples, X, df_returns):
        """
        This function applies a DBSCAN clustering algo

        :param eps: min distance for a sample to be within the cluster
        :param min_samples: min_samples to consider a cluster
        :param X: data

        :return: clustered_series_all: series with all tickers and labels
        :return: clustered_series: series with tickers belonging to a cluster
        :return: counts: counts of each cluster
        :return: clf object
        """
        clf = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean')
        #print(clf)

        clf.fit(X)
        labels = clf.labels_
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)
        print("Clusters discovered: %d" % n_clusters_)

        clustered_series_all = pd.Series(index=df_returns.columns, data=labels.flatten())
        clustered_series = clustered_series_all[clustered_series_all != -1]

        counts = clustered_series.value_counts()
        print("Pairs to evaluate: %d" % (counts * (counts - 1) / 2).sum())

        return clustered_series_all, clustered_series, counts, clf

    def clustering_for_optimal_PCA(self, min_components, max_components, returns, clustering_params):
        """
        This function experiments different values for the number of PCA components considered.
        It returns the values obtained for the number of components which provided the best silhouette
        coefficient.

        :param min_components: min number of components to test
        :param max_components: max number of components to test
        :param returns: series of returns
        :param clustering_params: parameters for clustering

        :return: X: PCA reduced dataset
        :return: clustered_series_all: cluster labels for all sample
        :return: clustered_series: cluster labels for samples belonging to a cluster
        :return: counts: counts for each cluster
        :return: clf: object returned by DBSCAN
        """
        # initialize dictionary to save best performers
        best_n_comp = {'n_comp': -1,
                       'silhouette': -1,
                       'X': None,
                       'clustered_series_all': None,
                       'clustered_series': None,
                       'counts': None,
                       'clf': None
                       }

        for n_comp in range(min_components, max_components):
            print('\nNumber of components: ', n_comp)
            # Apply PCA on data
            print('Returns shape: ', returns.shape)
            X, _ = self.apply_PCA(n_comp, returns)
            # Apply DBSCAN
            clustered_series_all, clustered_series, counts, clf = self.apply_DBSCAN(
                clustering_params['epsilon'],
                clustering_params['min_samples'],
                X,
                returns)
            # Silhouette score
            silhouette = silhouette_score(X, clf.labels_, 'euclidean')
            print('Silhouette score ', silhouette)

            # Standard deviation
            # std_deviation = counts.std()
            # print('Standard deviation: ',std_deviation))

            if silhouette > best_n_comp['silhouette']:
                best_n_comp = {'n_comp': n_comp,
                               'silhouette': silhouette,
                               'X': X,
                               'clustered_series_all': clustered_series_all,
                               'clustered_series': clustered_series,
                               'counts': counts,
                               'clf': clf
                               }

        print('\nThe best silhouette coefficient was: {} for {} principal components'.format(best_n_comp['silhouette'],
                                                                                             best_n_comp['n_comp']))

        return best_n_comp['X'], best_n_comp['clustered_series_all'], best_n_comp['clustered_series'], best_n_comp[
            'counts'], best_n_comp['clf']

    def get_candidate_pairs(self, clustered_series, pricing_df_train, pricing_df_test, n_clusters, min_half_life=5,
                            min_zero_crosings=20, p_value_threshold=0.05, hurst_threshold=0.5):
        """
        This function looks for tradable pairs over the clusters formed previously.

        :param clustered_series: series with cluster label info
        :param pricing_df_train: df with price series from train set
        :param pricing_df_test: df with price series from test set
        :param n_clusters: number of clusters
        :param min_half_life: min half life of a time series to be considered as candidate
        :param min_zero_crosings: min number of zero crossings (or mean crossings)
        :param p_value_threshold: p_value to check during cointegration test
        :param hurst_threshold: max hurst exponent value

        :return: list of pairs and its info
        :return: list of unique tickers identified in the candidate pairs universe
        """

        total_pairs = []
        for clust in range(n_clusters):
            symbols = list(clustered_series[clustered_series == clust].index)
            cluster_pricing_train = pricing_df_train[symbols]
            cluster_pricing_test = pricing_df_test[symbols]
            pairs = self.find_pairs(cluster_pricing_train,
                                    cluster_pricing_test,
                                    p_value_threshold,
                                    min_half_life,
                                    min_zero_crosings,
                                    hurst_threshold)
            total_pairs.extend(pairs)

        print('Found {} pairs'.format(len(total_pairs)))

        unique_tickers = np.unique([(element[0], element[1]) for element in total_pairs])
        print('The pairs contain {} unique tickers'.format(len(unique_tickers)))

        return total_pairs, unique_tickers