import sys, os, time, math, argparse, contextlib, random
import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
import pandas as pd
import matplotlib
import networkx as nx
import community
import phenograph
from matplotlib import offsetbox
import loader
from skimage.io import imsave
import sklearn
from sklearn.manifold import TSNE
from sklearn.metrics import adjusted_rand_score, silhouette_score, pairwise_distances
from sklearn.decomposition import PCA
from scipy.spatial.distance import pdist, squareform
from skimage.io import imsave
import seaborn as sns


def asinh(x, scale=5.):
    f = np.vectorize(lambda y: math.asinh(y/scale))

    return f(x) 

def sinh(x, scale=5.):

    return scale*np.sinh(x)

def softmax(x):

    return np.exp(x) / np.sum(np.exp(x), axis=1).reshape((-1,1))

def lrelu(x, leak=0.2, name="lrelu"):

  return tf.maximum(x, leak*x)

def tbn(name):

    return tf.get_default_graph().get_tensor_by_name(name)

def obn(name):

    return tf.get_default_graph().get_operation_by_name(name)

def to_one_hot(y, n):
    h = np.zeros((y.shape[0], n))
    h[np.arange(y.shape[0]), y] = 1
    return h

def plot(data, labels=None, title='', fn='', alpha=.3, s=2, fig=None, ax=None, marker='o', cmap=plt.cm.jet):
    if not ax:
        fig, ax = plt.subplots(1,1)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])

    if data.shape[1]>2:
        print("Can't plot input with >2 dimensions...")
        return 

    if labels is not None:
        r = list(range(data.shape[0]))
        np.random.shuffle(r)

        labels = labels[r]
        data = data[r,:]

        # reorder labels so that there are no missing labels between (0, l.max())
        for l in range(len(np.unique(labels))):
            if l != np.unique(labels)[l]:
                while l < np.unique(labels)[l]:
                    labels = np.where(labels>l, labels-1, labels)

        colors = [cmap(float(i)/(max(1,len(np.unique(labels)-1)))) for i in range(len(np.unique(labels)))]
        colors_ = [colors[int(l)] if l!=-1 else cm.Greys(.5) for l in labels]

        if len(np.unique(labels)) == 1: colors_ = cm.Greys(.5)

        ax.scatter(data[:,0], data[:,1], c=colors_, alpha=alpha, s=s, marker=marker)
    
    else:
        ax.scatter(data[:,0], data[:,1], alpha=alpha, s=s, marker=marker, c=cmap(0.))

    if fn:
        fig.savefig(os.path.join(args.save_folder,fn))
        plt.close('all')
        print("Plot saved to {}".format(fn))

def calculate_loss(sess, loader, train_or_test='test'):
    loss_tensor = tbn('loss:0')
    x_tensor = tbn('x:0')
    y_tensor = tbn('y:0')
    losses = []
    for batch, batch_labels in loader.iter_batches(train_or_test):
        feed = {x_tensor:batch,
                y_tensor:batch,
                tbn('is_training:0'):False}
        [l] = sess.run([loss_tensor], feed_dict=feed)
        losses.append(l)

    avg_loss = sum(losses) / float(len(losses))
    return avg_loss

def count_clusters(sess, loader, layer, thresh=0, return_clusters=False, BIN_MIN=50, scope=None):
    '''Counts the number of clusters after binarizing the activations of the given layer.'''
    #acts, labels = get_layer(sess, loader, 'normalized_activations_layer_{}:0'.format(layer))
    acts, labels = get_layer(sess, loader, 'layer_encoder_{}_activation'.format(layer), scope=scope)

    unique_argmaxes, unique_argmaxes_counts = np.unique(acts.argmax(axis=1), return_counts=True)
    unique_argmaxes_counts = list(reversed(sorted(unique_argmaxes_counts.tolist())))
    # for i in range(len(unique_argmaxes)):
    #     if i>10: break
    #     print(unique_argmaxes[i], unique_argmaxes_counts[i])
    # print("Max neuron values: ", acts.max(axis=1)[:5], "...")
    # print("Number of unique max neurons: ", len(np.unique(acts.argmax(axis=1))))


    binarized = np.where(acts>thresh, 1, 0)

    # k = 10
    # binarized = np.zeros(acts.shape)
    # topk = np.argpartition(acts, -k, axis=1)[:,-k:]
    # for i,row in enumerate(topk):
    #     for j in row:
    #         binarized[i,j] = 1
    unique_rows, counts = np.unique(binarized, axis=0, return_counts=True)
    unique_rows = unique_rows[counts>BIN_MIN]

    #unique_rows = np.vstack({tuple(row) for row in binarized})
    num_clusters = unique_rows.shape[0]
    r = list(range(num_clusters))
    random.shuffle(r)
    unique_rows = unique_rows[r,:]
    print(num_clusters)
    if num_clusters>5000:
        print("Too many clusters to go through...")
        return None, None
    
    num_clusters = 0
    rows_clustered = 0
    new_labels = -1*np.ones(labels.shape)
    for i,row in enumerate(unique_rows):
        if i and i%100==0:
            print(i)
        rows_equal_to_this_code = np.where(np.all(binarized==row, axis=1))[0]

        new_labels[rows_equal_to_this_code] = num_clusters
        num_clusters += 1
        rows_clustered += rows_equal_to_this_code.shape[0]

    print("---- Num clusters: {} ---- Pct clustered: {:.3f} ----".format(num_clusters, 1.*rows_clustered/new_labels.shape[0]))

    if return_clusters:
        return num_clusters, new_labels 

    if return_clusters:
        return num_clusters, new_labels 
    return num_clusters     

def channel_by_cluster(sess, loader, layer, cols, ax=None, savefile=None, zscore=False, BIN_MIN=50, fig_cbar=None, fig=None, clusters=None):
    x, labels = get_layer(sess, loader, 'x')
    x = np.where(x<0, 0, x)

    if clusters is None:
        count, clusters = count_clusters(sess, loader, layer, thresh=0, return_clusters=True, BIN_MIN=BIN_MIN)
        
    x = x[clusters!=-1,:]
    clusters = clusters[clusters!=-1]

    df = pd.DataFrame(x)
    print(df.shape)
    df['cluster'] = clusters

    grouped = df.groupby('cluster')
    means = grouped.apply(lambda x: x.mean(axis=0))
    del means['cluster']

    if zscore:
        means = (means - means.mean(axis=0)) / (means.std(axis=0))

    min_ = means.min().min()
    max_ = means.max().max()

    normalizer = colors.Normalize(min_, max_)
    means = normalizer(means)
    means = means.data

    imshowax = ax.imshow(means.transpose(), cmap='jet')
    ax.set_yticks(range(len(cols)))
    ax.set_yticklabels([c for c in cols])
    ax.set_xticks([])
    ax.set_ylabel('Marker')
    ax.set_xlabel('Cluster')

    if savefile:
        fig.savefig(args.save_folder+savefile)
    if fig_cbar:
        cbar = fig_cbar.colorbar(imshowax)
        cbar.set_ticks([0,.5,1])
        cbar.set_ticklabels(['{:.2f}'.format(min_), '{:.2f}'.format((min_+max_)/2.), '{:.2f}'.format(max_)])


    return imshowax

def calculate_mmd(k1, k2, k12):

    return k1.sum()/(k1.shape[0]*k1.shape[1]) + k2.sum()/(k2.shape[0]*k2.shape[1]) - 2*k12.sum()/(k12.shape[0]*k12.shape[1])

def np_to_tfrecords(X, Y, file_path_prefix, verbose=True):
    def _dtype_feature(ndarray):
        assert isinstance(ndarray, np.ndarray)
        dtype_ = ndarray.dtype
        if dtype_ == np.float64 or dtype_ == np.float32:
            return lambda array: tf.train.Feature(float_list=tf.train.FloatList(value=array))
        elif dtype_ == np.int64:
            return lambda array: tf.train.Feature(int64_list=tf.train.Int64List(value=array))
        else:
            raise ValueError("The input should be numpy ndarray. \
                               Instaed got {}".format(ndarray.dtype))

    assert isinstance(X, np.ndarray)
    assert len(X.shape) == 2  # If X has a higher rank,
                               # it should be rshape before fed to this function.
    assert isinstance(Y, np.ndarray) or Y is None

    # load appropriate tf.train.Feature class depending on dtype
    dtype_feature_x = _dtype_feature(X)
    if Y is not None:
        assert X.shape[0] == Y.shape[0]
        assert len(Y.shape) == 2
        dtype_feature_y = _dtype_feature(Y)

    # Generate tfrecord writer
    result_tf_file = file_path_prefix + '.tfrecords'
    writer = tf.python_io.TFRecordWriter(result_tf_file)
    if verbose:
        print("Serializing {:d} examples into {}".format(X.shape[0], result_tf_file))

    # iterate over each sample,
    # and serialize it as ProtoBuf.
    for idx in range(X.shape[0]):
        x = X[idx]
        if Y is not None:
            y = Y[idx]

        d_feature = {}
        d_feature['X'] = dtype_feature_x(x)
        if Y is not None:
            d_feature['Y'] = dtype_feature_y(y)

        features = tf.train.Features(feature=d_feature)
        example = tf.train.Example(features=features)
        serialized = example.SerializeToString()
        writer.write(serialized)

    if verbose:
        print("Writing {} done!".format(result_tf_file))

def create_legend(npts, ax, cmap=cm.jet):
    lhs = []
    for pt in range(npts):
        lh = matplotlib.collections.CircleCollection([8], label='{:.0f}'.format(pt), color=cmap(pt/npts))
        lhs.append(lh)
    leg = ax.legend(title='SAUCIE cluster', handles=lhs, handletextpad=0, ncol=3, columnspacing=.03, loc='center')

def convert_reconstruction_to_input(load, saucie, thresh_min=0, thresh_max=None, scope=None):
    recon_, labels = get_layer(saucie.sess, load, 'layer_output_activation', scope=scope)
    if isinstance(thresh_min, int):
        recon_ = np.where(recon_<thresh_min,thresh_min,recon_)
    if isinstance(thresh_max, int):
        recon_ = np.where(recon_<thresh_max,thresh_max,recon_)
    load.data = recon_
    return load

def save_images(save_directory, embeddings, clusters, clusters_louvain, saucie, load, layer=2):
    # embedding scatter plot
    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(embeddings, clusters, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'embedded_clusters_saucie'))

    
    # embedding scatter plot legend
    fig, ax = plt.subplots(1,1)
    create_legend(len(np.unique(clusters[clusters!=-1])), ax=ax)
    fig.savefig(os.path.join(save_directory, 'embedded_clusters_saucie_legend'))

    # cluster by channel heatmap and colorbar
    fig,ax = plt.subplots(1,1, figsize=(9,9))
    fig.subplots_adjust(top=.99,right=.99, bottom=.1, left=.1)

    figcbar = plt.figure()
    figcbar.subplots_adjust(top=.99,right=.99, bottom=.1, left=.1)
    channel_by_cluster(saucie.sess, load, layer, load.get_colnames(), ax=ax, clusters=clusters, fig_cbar=figcbar)

    fig.savefig(os.path.join(save_directory, 'clusters_saucie_heatmap'))
    figcbar.savefig(os.path.join(save_directory, 'clusters_saucie_heatmap_colorbar'))

    # saucie/louvain comparison on tsne scatter
    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(load.xtsne[:clusters.shape[0]], clusters, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'tsne_clusters_saucie'))

    
    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(load.xtsne[:clusters.shape[0]], clusters_louvain, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'tsne_clusters_louvain'))

    # saucie/louvain comparison on saucie scatter
    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(embeddings, clusters_louvain, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'embedded_clusters_louvain'))

    # tsne/pca/saucie, no labels
    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(load.xtsne, None, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'nolabels_tsne'))

    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    pca = sklearn.decomposition.PCA(2)
    pcadata = pca.fit_transform(load.data)
    plot(pcadata, None, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'nolabels_pca'))

    fig, ax = plt.subplots(1,1)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plot(embeddings, None, ax=ax, alpha=1)
    fig.savefig(os.path.join(save_directory, 'nolabels_saucie'))





















