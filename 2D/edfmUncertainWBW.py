# -*- coding: utf-8 -*-
"""Untitled0.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1hFlfNDw_Deq98ki9PTIwXxqYFPlLL34b
"""
#import os
# Grab specific GPU
#os.environ["CUDA_DIVICE_ORDER"] = "PCI_BUS_ID"
#os.environ["CUDA_VISIBLE_DEVICES"]="3"

import tensorflow as tf
import numpy as np
from tensorflow import keras
#from sklearn.preprocessing import MinMaxScaler
		
# Specify initial seed to get consistent result
# tf.set_random_seed(1)

# Parameters
n_neurons = 200
n_layers = 1
n_PRD = 4
n_INJ = 1
learning_rate = 0.001
n_iterations =800000 # training maximum iteration
trainingRatio = 0.6 # ratio of training set from example
trainTerminationLoss = 0.10
dummy = 5  # added to water PRD sample to handle loss calculation
grid_Nx = 240
grid_Ny =240
n_real = 20

# Arrange data -local GPU
BHPtraining = np.loadtxt('BHPtraining.csv', delimiter=',', dtype = np.float32)
ratestraining = np.loadtxt('YWBW_all.csv', delimiter=',', dtype = np.float32)

#MinMax Scaler input feature
#scaler = MinMaxScaler()
#Permtraining = scaler.fit_transform(Permtraining)
#BHPtraining =scaler.fit_transform(BHPtraining)

# Calculated from user specified parameters
n_outputs = 2*n_PRD+n_INJ
n_steps = ratestraining.shape[1]//(2*n_PRD+n_INJ)
n_inputs = n_PRD + n_INJ
m = ratestraining.shape[0]

# Build image dataset - Permeability map
# In EDFM, PermdataX is single phase steady state P map
steadyP = np.zeros([n_real, grid_Nx*grid_Ny])
for i in range(n_real):
	pdata = np.loadtxt('input/SteadyState_P_'+str(i+1)+'.dat')
	steadyP[i,:] = pdata
steadyP = (steadyP-140)/(435-140)
Permtraining = np.tile(steadyP,(int(m/n_real),1))
PermdataX = np.reshape(Permtraining,(m, grid_Nx, grid_Ny,1))

# Build Time-series dataset -BHP profile and well rates
# BHPdata = PermBHPtraining[:,grid_Nx*grid_Ny:]
BHPdataX = np.reshape(BHPtraining,(m, n_steps, n_inputs))
WelldataY = np.reshape(ratestraining,(m, n_steps, n_outputs))

# custom training loss
def trainloss(y_true, y_pred):
  loss = tf.reduce_mean(tf.reduce_sum(tf.abs(y_pred-y_true),1)/tf.reduce_sum(y_true,1))
  return loss

# custom termination loss
def termloss(y_true, y_pred):
  ter_loss = tf.reduce_mean(tf.reduce_sum(tf.abs(y_pred[:,1:,:]-y_true[:,1:,:]),1)/tf.reduce_sum(y_true[:,1:,:],1))
  return ter_loss

# Divide train/Dev
train_size = int(m * trainingRatio)
test_size = m - train_size
PermtrainX, PermdevX = np.array(PermdataX[0:train_size,:,:,:]), np.array(PermdataX[train_size:m,:,:,:])
BHPtrainX, BHPdevX = np.array(BHPdataX[0:train_size,:,:,]), np.array(BHPdataX[train_size:m,:,:,])
trainY, devY = np.array(WelldataY[0:train_size,:,:]), np.array(WelldataY[train_size:m,:,:])

train_cost = []
dev_cost = []
train_ter_cost = []
dev_ter_cost = []

# Build combined CNN-RNN network. CNN process permeability image to generate initial longterm and shortterm states in LSTM RNN
# Build CNN
perminput = keras.layers.Input(shape=[grid_Nx,grid_Ny,1])
conv1 = tf.keras.layers.Conv2D(4, [3,3], strides=(1, 1), padding='same')(perminput)
bn1 = tf.keras.layers.BatchNormalization()(conv1)
act1 = tf.nn.relu(bn1)
pool1 = tf.keras.layers.MaxPool2D((2,2))(act1)
conv2 = tf.keras.layers.Conv2D(8, [3,3], strides=(1, 1), padding='same')(pool1)
bn2 = tf.keras.layers.BatchNormalization()(conv2)
act2 = tf.nn.relu(bn2)
pool2 = tf.keras.layers.MaxPool2D((2,2))(act2)
conv3 = tf.keras.layers.Conv2D(16, [3,3], strides=(1, 1), padding='same')(pool2)
bn3 = tf.keras.layers.BatchNormalization()(conv3)
act3 = tf.nn.relu(bn3)
pool3 = tf.keras.layers.MaxPool2D((2,2))(act3)
flatten = tf.keras.layers.Flatten()(pool3)
ht = tf.keras.layers.Dense(n_neurons)(flatten) # LSTM initial short term state
ct = tf.keras.layers.Dense(n_neurons)(flatten) # LSTM initial long term state
# Build LSTM
bhpinput = keras.layers.Input(shape=[n_steps,n_inputs])
lstm1 = keras.layers.LSTM(n_neurons, return_sequences=True,activation='relu')(bhpinput,initial_state=[ht,ct])
y_pred = keras.layers.Dense(n_outputs)(lstm1)

model = keras.Model(inputs=[perminput,bhpinput],outputs=[y_pred])
opt = keras.optimizers.Adam(learning_rate = learning_rate,clipnorm=5)
model.compile(loss=trainloss,optimizer=opt,metrics=[termloss])

#model.summary()

Termloss = 1000
iteration = 0
while iteration < n_iterations and Termloss > trainTerminationLoss:
  history = model.fit((PermtrainX,BHPtrainX),trainY,batch_size=train_size,verbose=0,epochs=200,validation_data=((PermdevX,BHPdevX),devY))
  Trainloss, Termloss = model.evaluate((PermtrainX,BHPtrainX),trainY,batch_size=train_size)
  #devMSE,TerdevMse = model.evaluate((PermdevX,BHPdevX),devY,batch_size=test_size)
  #dev_cost.append(devMse)
  #dev_ter_cost.append(TerdevMse)
  train_cost.append(Trainloss)
  train_ter_cost.append(Termloss)
  iteration = iteration + 1

# Save trained network on Result folder
model.save("WBWall.h5")

# Save iteration vs cost
devMse,TerdevMse = model.evaluate((PermdevX,BHPdevX),devY,batch_size=test_size)
dev_cost.append(devMse)
dev_ter_cost.append(TerdevMse)
np.savetxt("trainCost.txt", train_cost)
np.savetxt("devCost.txt", dev_cost)
np.savetxt("trainTerCost.txt", train_ter_cost)
np.savetxt("devTerCost.txt", dev_ter_cost)

# Predict response using the trained model and save data to analyze using MATLAB.
Y_new = model.predict((PermdevX,BHPdevX))
Y_new = Y_new.reshape(test_size,n_steps*(2*n_PRD+n_INJ))
np.savetxt("DevWBWall.csv",Y_new,delimiter=",")

# Training set prediction
Y_training_pred = model.predict((PermtrainX,BHPtrainX))
Y_training_pred = Y_training_pred.reshape(train_size,n_steps*(2*n_PRD+n_INJ))
np.savetxt("TrainingWBWall.csv", Y_training_pred, delimiter =",")

'''
# Divide Y_new and Y_training_pred into separate water INJ, oil PRD, and water PRD files and save
waterINJ_new = np.zeros((test_size, n_steps*n_INJ))
oilPRD_new = np.zeros((test_size, n_steps*n_PRD))
waterPRD_new = np.zeros((test_size, n_steps*n_PRD))
waterINJ_training = np.zeros((train_size, n_steps*n_INJ))
oilPRD_training = np.zeros((train_size, n_steps*n_PRD))
waterPRD_training = np.zeros((train_size, n_steps*n_PRD))

for time in range(n_steps):
	waterINJ_new[:,n_INJ*time:n_INJ*time+n_INJ] = np.maximum(dummy,np.array(Y_new[:,(2*n_PRD+n_INJ)*time:(2*n_PRD+n_INJ)*time+n_INJ]))
	oilPRD_new[:,n_PRD*time:n_PRD*time+n_PRD] = np.maximum(dummy,np.array(Y_new[:,(2*n_PRD+n_INJ)*time+n_INJ:(2*n_PRD+n_INJ)*time+n_INJ+n_PRD]))
	waterPRD_new[:,n_PRD*time:n_PRD*time+n_PRD] = np.maximum(dummy,np.array(Y_new[:,(2*n_PRD+n_INJ)*time+n_INJ+n_PRD:(2*n_PRD+n_INJ)*time+n_INJ+n_PRD+n_PRD]))
	waterINJ_training[:,n_INJ*time:n_INJ*time+n_INJ] = np.maximum(dummy,np.array(Y_training_pred[:,(2*n_PRD+n_INJ)*time:(2*n_PRD+n_INJ)*time+n_INJ]))
	oilPRD_training[:,n_PRD*time:n_PRD*time+n_PRD] = np.maximum(dummy,np.array(Y_training_pred[:,(2*n_PRD+n_INJ)*time+n_INJ:(2*n_PRD+n_INJ)*time++n_INJ+n_PRD]))
	waterPRD_training[:,n_PRD*time:n_PRD*time+n_PRD] = np.maximum(dummy,np.array(Y_training_pred[:,(2*n_PRD+n_INJ)*time+n_INJ+n_PRD:(2*n_PRD+n_INJ)*time++n_INJ+n_PRD+n_PRD]))

waterPRD_new = waterPRD_new - dummy # subtract dummy
waterPRD_training = waterPRD_training - dummy
waterINJ_new = waterINJ_new - dummy # subtract dummy
waterINJ_training = waterINJ_training - dummy
oilPRD_new = oilPRD_new - dummy # subtract dummy
oilPRD_training = oilPRD_training - dummy

np.savetxt("DevWBWoil.csv", oilPRD_new, delimiter = ",")
np.savetxt("DevWBWwaterINJ.csv", waterINJ_new, delimiter = ",")
np.savetxt("DevWBWwaterPRD.csv", waterPRD_new, delimiter = ",")
np.savetxt("TrainingWBWoil.csv", oilPRD_training, delimiter = ",")
np.savetxt("TrainingWBWwaterINJ.csv", waterINJ_training, delimiter = ",")
np.savetxt("TrainingWBWwaterPRD.csv", waterPRD_training, delimiter = ",")
'''




