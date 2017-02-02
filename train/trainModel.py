# -*- coding: utf-8 -*-
#
# Birdsong classificatione in noisy environment with convolutional neural nets in Keras
# Copyright (C) 2017 Báint Czeba, Bálint Pál Tóth (toth.b@tmit.bme.hu)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>. (c) Balint Czeba, Balint Pal Toth
# 
# Please cite the following paper if this code was useful for your research:
# 
# Bálint Pál Tóth, Bálint Czeba,
# "Convolutional Neural Networks for Large-Scale Bird Song Classification in Noisy Environment", 
# In: Working Notes of Conference and Labs of the Evaluation Forum, Évora, Portugália, 2016, p. 8

# this script is responsible for training the neural networks

from scipy import io
import pandas as pd
import numpy as np
import time
import pickle
import os
import h5py
import sys, getopt
import datetime
from MapCallback import MapCallback

if __name__ == "__main__":
    argv=sys.argv[1:]

nb_epochs	= 20000 # number of epochs, should be high, the end of the learning process is controled by early stoping
es_patience	= 100 # patience for early stoping 
batchSize	= 1350 # batch size for mini-batch training
hdf5path	= '../birdclef_data/data_top999_nozero.hdf5' # training data generated by loadData.py
modelPath	= './model-AlexNet.py' # filename of the model to use (currently model-birdClef.py or model-AlexNet.py)
logfileName	= 'log.xls'
#scalerFilePath	= '../birdclef_data/standardScaler_5000.pickle'
scalerFilePath	= None
preTrainedModelWeightsPath = None # path and filename to pretrained network: if there is a pretrained network, we can load it and continue to train it
tensorflowBackend = False # set true if Keras has TensorFlow backend - this way we set TF not to allocate all the GPU memory

if (tensorflowBackend):
	import tensorflow as tf
	config = tf.ConfigProto()
	config.gpu_options.allow_growth=True
	sess = tf.Session(config=config)
	from keras import backend as K
	K.set_session(sess)

print('nb_epochs: %d, hdf5path: %s, scalerFilePath: %s' % (nb_epochs, hdf5path,scalerFilePath))

scaler = None
scaleData = None
# if a scaler file generated by loadData.py is given, than load it and define a scaler function that will be used later
if scalerFilePath is not None:
    scaler = pickle.load(open(scalerFilePath, 'rb'))
    # Can't use scaler.transform because it only supports 2d arrays.
    def scaleData(X):
        return (X-scaler.mean_)/scaler.scale_

from io_utils_mod import HDF5Matrix
f = h5py.File(hdf5path, 'r')
X = f.get('X')
y = f.get('y')
print("Shape of X: ")
print(X.shape)
dataSetLength	= X.shape[0]
output_dim	= y.shape[1] #len(y_train[0])
# test and validation splits
testSplit	= 0.01 # 1%
validationSplit	= 0.05 # 5%
f.close()
# load training data
X_train = HDF5Matrix(hdf5path, 'X', 0, int(dataSetLength*(1-(testSplit+validationSplit))), normalizer = scaleData) 
y_train = HDF5Matrix(hdf5path, 'y', 0, int(dataSetLength*(1-(testSplit+validationSplit))))
# load validation data
X_validation = HDF5Matrix(hdf5path, 'X', int(dataSetLength*(1-(testSplit+validationSplit)))+1, int(dataSetLength*(1-testSplit)), normalizer = scaleData)
y_validation = HDF5Matrix(hdf5path, 'y', int(dataSetLength*(1-(testSplit+validationSplit)))+1, int(dataSetLength*(1-testSplit)))
# load test data
X_test = HDF5Matrix(hdf5path, 'X', int(dataSetLength*(1-testSplit))+1, dataSetLength, normalizer = scaleData)
y_test = HDF5Matrix(hdf5path, 'y', int(dataSetLength*(1-testSplit))+1, dataSetLength)

print("Shape of X_train after train-validation-test split:")
print(X_train.shape)

# store the starting time 
startTime = time.time()

# load model and compile it, we use RMSprop here, other optimizer algorithm should be tested
execfile(modelPath)
model.compile(loss='categorical_crossentropy', optimizer='rmsprop')#, metrics=["accuracy"])

# print the model
print("The following model is used: ")
for layer in model.layers:
    print("{} output shape: {}".format(layer.name, layer.output_shape))

# load pretrained model if it is set
if preTrainedModelWeightsPath is not None:
    model.load_weights(preTrainedModelWeightsPath)
    print("Reloaded weights from: {}".format(preTrainedModelWeightsPath))

# define callback functions
mapcallback	= MapCallback()
earlyStopping	= EarlyStopping(monitor='val_loss', patience = es_patience) # early stoping
# save best models based on accuracy, loss and MAP metrics
bestModelFilePath_val_acc	= './modelWeights/best_val_acc_{}_{}.hdf5'.format(output_dim, datetime.datetime.now().strftime('%Y-%m-%d-%M-%S'))
bestModelFilePath_val_loss	= './modelWeights/best_val_loss_{}_{}.hdf5'.format(output_dim, datetime.datetime.now().strftime('%Y-%m-%d-%M-%S'))
#bestModelFilePath_val_map	= './modelWeights/best_val_map_{}_{}.hdf5'.format(output_dim, datetime.datetime.now().strftime('%Y-%m-%d-%M-%S'))
bestModelFilePath_val_map	= './modelWeights/best_val_map_{}.hdf5'.format(output_dim)
checkpointer_val_acc	= ModelCheckpoint(filepath = bestModelFilePath_val_acc, verbose = 1, monitor = 'val_acc', save_best_only = True)
checkpointer_val_loss	= ModelCheckpoint(filepath = bestModelFilePath_val_loss, verbose = 1, monitor = 'val_loss', save_best_only = True)
checkpointer_val_map	= ModelCheckpoint(filepath = bestModelFilePath_val_map, verbose = 1, monitor = 'val_map', mode = 'max', save_best_only = True)

# training
fitting_result	= model.fit(X_train, y_train, nb_epoch = nb_epochs, batch_size = batchSize, callbacks = [earlyStopping, mapcallback, checkpointer_val_acc, checkpointer_val_loss,  checkpointer_val_map], shuffle = 'batch', validation_data = (X_validation, y_validation))

# calculate the elapsed time
elapsed = time.time()-startTime;
print("Execution time: {0} s".format(elapsed))

# convert the output (probabilistics) to classes
def proba_to_class(a):
    classCount	= len(a[0])
    to_return	= np.empty((0,classCount))
    for row in a:
        maxind	= np.argmax(row)
        to_return = np.vstack((to_return, [1 if i == maxind else 0 for i in range(classCount)]))
    return to_return

# calculate metrics on test data with the last model 
from sklearn.metrics import average_precision_score, accuracy_score
y_result	= model.predict(X_test)
map		= average_precision_score( y_test.data[y_test.start: y_test.end], y_result, average='micro')
accuracy	= accuracy_score(y_test.data[y_test.start: y_test.end], proba_to_class(y_result))
print("AveragePrecision: {}".format(map))
print("Accuracy: {}".format(accuracy))

# reload the best model with smallest validation loss and calculate metrics on test data
print("----- Loading best model from: {}  -------".format(bestModelFilePath_val_loss))
model.load_weights(bestModelFilePath_val_loss)
y_result_bm		= model.predict(X_test)
map_bm_val_loss		= average_precision_score( y_test.data[y_test.start: y_test.end], y_result_bm, average='macro')
accuracy_bm_val_loss	= accuracy_score(y_test.data[y_test.start: y_test.end], proba_to_class(y_result_bm))
print("AveragePrecision: {}".format(map_bm_val_loss))
print("Accuracy: {}".format(accuracy_bm_val_loss))

# reload the best model with highest validation accuracy and calculate metrics on test data
print("----- Loading best model from: {}  -------".format(bestModelFilePath_val_acc))
model.load_weights(bestModelFilePath_val_acc)
y_result_bm		= model.predict(X_test)
map_bm_val_acc		= average_precision_score( y_test.data[y_test.start: y_test.end], y_result_bm, average='macro')
accuracy_bm_val_acc	= accuracy_score(y_test.data[y_test.start: y_test.end], proba_to_class(y_result_bm))
print("AveragePrecision: {}".format(map_bm_val_acc))
print("Accuracy: {}".format(accuracy_bm_val_acc))

# save the results summery into an excel file
import log
log.logToXLS(logfileName, model, fitting_result, {'execution(s)':elapsed, 'map':map, 'accuracy':accuracy, 'map_bm_val_loss':map_bm_val_loss, 'accuracy_bm_val_loss':accuracy_bm_val_loss,'map_bm_val_acc':map_bm_val_acc, 'accuracy_bm_val_acc':accuracy_bm_val_acc, 'modelPyFile': modelPath})
