# -*- coding: utf-8 -*-
"""Karaoke-MASTER.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1dp-SB0nUdJ0NKloIeXLl_AmCr7xDj6x-

# Karaoke MASTER (ver. 1.0)

***

## GPT2-based Karaoke Melody Artificial Intelligence Model Creator/Trainer.

***

Credit for char-based GPT2 implementation used in this colab goes out to Andrej Karpathy: https://github.com/karpathy/minGPT

***

WARNING: This complete implementation is a functioning model of the Artificial Intelligence. Please excercise great humility, care, and respect.

***

##### Project Los Angeles

##### Tegridy Code 2021

***

# Setup Environment, clone needed repos, and install all required dependencies
"""

#@title Install all dependencies (run only once per session)
!git clone https://github.com/asigalov61/minGPT
!git clone https://github.com/asigalov61/tegridy-tools
!apt install fluidsynth #Pip does not work for some reason. Only apt works
!pip install midi2audio

# Commented out IPython magic to ensure Python compatibility.
#@title Import all needed modules

print('Loading needed modules. Please wait...')
import os
import copy

from operator import itemgetter
from itertools import groupby

os.chdir('/content/tegridy-tools/tegridy-tools')
import TMIDI

if not os.path.exists('/content/Dataset'):
    os.makedirs('/content/Dataset')

os.chdir('/content/minGPT')

# make deterministic
from mingpt.utils import set_seed
set_seed(42)

import tqdm.auto
import pickle
import numpy as np
import torchvision
import torch
import torch.nn as nn
from torch import optim
import torch.nn.functional as F
from torch.utils.data import Dataset

import keras
from keras.utils import to_categorical

import time
import math
import datetime
from datetime import datetime

from mingpt.model import GPT, GPTConfig
from mingpt.trainer import Trainer, TrainerConfig
from mingpt.utils import sample

import tqdm.auto

import matplotlib
import matplotlib.pyplot as plt
# %matplotlib inline

from midi2audio import FluidSynth
from IPython.display import display, Javascript, HTML, Audio

from google.colab import output, drive

dtype = torch.float
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
# Assume that we are on a CUDA machine, then this should print a CUDA device:

print('Available Processing Device is:', device)
print('Loading complete. Enjoy! :)')

os.chdir('/content/')

"""# Download and process MIDI dataset"""

# Commented out IPython magic to ensure Python compatibility.
#@title Download Tiny Karaoke MIDI dataset

#@markdown Works best stand-alone/as-is for the optimal results
# %cd /content/Dataset/
!wget 'https://github.com/asigalov61/Tegridy-MIDI-Dataset/raw/master/Tiny-Karaoke-MIDI-Dataset-CC-BY-NC-SA.zip'
!unzip -j '/content/Dataset/Tiny-Karaoke-MIDI-Dataset-CC-BY-NC-SA.zip'
!rm '/content/Dataset/Tiny-Karaoke-MIDI-Dataset-CC-BY-NC-SA.zip'
# %cd /content/

"""# If you are not sure where to start or what settings to select, please use original defaults"""

# Commented out IPython magic to ensure Python compatibility.
#@title Process MIDIs to special MIDI dataset with Tegridy MIDI Processor

full_path_to_output_dataset_to = "/content/Karaoke-MASTER" #@param {type:"string"}
#@title Convert MIDI dataset to the Reduced TXT Karaoke dataset

#@markdown Make sure to select the right encoding for your language. Encoding is correct when you can properly and clearly read it in your language. Encodings list is located here: https://docs.python.org/3/library/codecs.html#standard-encodings

full_path_to_TXT_dataset = "/content/Karaoke-MASTER_TXT_Dataset.txt" #@param {type:"string"}
karaoke_language_encoding = "utf_8" #@param {type:"string"}
dataset_name = "DATASET=Karaoke-MASTER_TXT_Dataset"

# %cd /content/

print('TMIDI Processor')
print('Starting up...')

events_list = []
events_matrix = []

###########

files_count = 0

mev = 0
kev = 0

TXT = ''

chords_list_f = []
melody_list_f = []

print('Loading MIDI files...')
print('This may take a while on a large dataset in particular.')

dataset_addr = "/content/Dataset/"
os.chdir(dataset_addr)
filez = os.listdir(dataset_addr)

print('Processing MIDI files. Please wait...')
for f in tqdm.auto.tqdm(filez):
  files_count += 1

  events_matrix, mev, kev = TMIDI.Tegridy_Karaoke_MIDI_to_Reduced_TXT_Processor(f, karaoke_language_encoding)
  TXT += events_matrix

TMIDI.Tegridy_TXT_Dataset_File_Writer(full_path_to_TXT_dataset, '', dataset_name + '\n' + TXT)

"""# Setup and Intialize the Model

## YOU MUST RUN ALL CELLS/CODE IN THIS SECTION to init the model. Does not matter if the model is empty or pre-trained.

## DO NOT EXECUTE TRAIN CELL/CODE UNLESS YOU INTEND TO TRAIN FROM SCRATCH
"""

#@title Setup functions and procedures
model_attention_span_in_tokens = 512 #@param {type:"slider", min:0, max:1024, step:16}

class CharDataset(Dataset):

    def __init__(self, data, block_size):
        chars = sorted(list(set(data)))
        data_size, vocab_size = len(data), len(chars)
        print('data has %d characters, %d unique.' % (data_size, vocab_size))
        
        self.stoi = { ch:i for i,ch in enumerate(chars) }
        self.itos = { i:ch for i,ch in enumerate(chars) }
        self.block_size = block_size
        self.vocab_size = vocab_size
        self.data = data
    
    def __len__(self):
        return len(self.data) - self.block_size

    def __getitem__(self, idx):
        # grab a chunk of (block_size + 1) characters from the data
        chunk = self.data[idx:idx + self.block_size + 1]
        # encode every character to an integer
        dix = [self.stoi[s] for s in chunk]
        
        x = torch.tensor(dix[:-1], dtype=torch.long)
        y = torch.tensor(dix[1:], dtype=torch.long)
        return x, y

        
block_size = model_attention_span_in_tokens # spatial extent of the model for its context

#@title Specify full path to the processed TMIDI-TXT dataset file
full_path_to_training_text_file = "/content/Karaoke-MASTER_TXT_Dataset.txt" #@param {type:"string"}
text = open(full_path_to_training_text_file, 'r').read() # don't worry we won't run out of file handles
train_dataset = CharDataset(text, block_size) # one line of poem is roughly 50 characters

#@title Create GPT2 model
model_embed_size = 256 #@param {type:"slider", min:0, max:1024, step:64}
number_of_heads = 16 #@param {type:"slider", min:1, max:16, step:1}
number_of_layers = 4 #@param {type:"slider", min:1, max:16, step:1}


mconf = GPTConfig(train_dataset.vocab_size, 
                  train_dataset.block_size,
                  n_layer=number_of_layers, 
                  n_head=number_of_heads, 
                  n_embd=model_embed_size)

model = GPT(mconf)

#@title Setup all training parameters
number_of_training_epochs = 2 #@param {type:"slider", min:1, max:5, step:1}
training_batch_size = 48 #@param {type:"slider", min:0, max:160, step:4}
model_learning_rate = 6e-4 #@param {type:"number"}
# initialize a trainer instance and kick off training

tconf = TrainerConfig(max_epochs=number_of_training_epochs, 
                      batch_size=training_batch_size, 
                      learning_rate=model_learning_rate,
                      num_workers=4)
trainer = Trainer(model, train_dataset, None, tconf)

"""# Train the model or Load/Re-load the existing pre-trained model checkpoint"""

# Commented out IPython magic to ensure Python compatibility.
#@title (OPTION 1) Train the model
# %cd /content/
trainer.train()

#@title Plot Positional Embeddings

# visualize some of the learned positional embeddings, maybe they contain structure
plt.figure(figsize=(18, 1))  
ci = model.pos_emb.data[0, :, 0].cpu()
zci = torch.cat((torch.tensor([0.0]), ci)) # pre-cat a zero
plt.imshow(zci.view(1, block_size+1).numpy())
plt.axis('off')

# Commented out IPython magic to ensure Python compatibility.
#@title Save/Re-Save the model from memory
#@markdown Standard PyTorch AI models file extension is PTH
full_path_to_save_model_to = "/content/Karaoke-MASTER-Trained-Model.pth" #@param {type:"string"}
# %cd /content/
torch.save(model, full_path_to_save_model_to)

#@title (OPTION 2) Load existing model/checkpoint
full_path_to_model_checkpoint = "/content/Karaoke-MASTER-Trained-Model.pth" #@param {type:"string"}
model = torch.load(full_path_to_model_checkpoint)
model.eval()

"""# Generate, download, plot, and listen to the output"""

#@title Generate and download the composition as TXT file.
#@markdown PLEASE NOTE IMPORTANT POINTS: 

#@markdown 0) If you are not sure where to start/what settings to set, please use original defaults.

#@markdown 1) Model primes from the dataset !!!

#@markdown 2) Model's first output may be empty or garbled so please try several times before discarting the model

print('Karaoke MASTER Model Generator')
print('Starting up...')
number_of_tokens_to_generate = 2048 #@param {type:"slider", min:0, max:32768, step:128}
creativity_temperature = 0.8 #@param {type:"slider", min:0.05, max:4, step:0.05}
top_k_prob = 4 #@param {type:"slider", min:0, max:50, step:1}
input_prompt = "Love" #@param {type:"string"}

debug = False 

os.chdir('/content/')

model.to(device)

context = input_prompt
x = torch.tensor([train_dataset.stoi[s] for s in context], dtype=torch.long)[None,...].to(trainer.device)
y = sample(model, x, number_of_tokens_to_generate, temperature=creativity_temperature, sample=True, top_k=top_k_prob)[0]
completion = ''.join([train_dataset.itos[int(i)] for i in y])

fname = TMIDI.Tegridy_File_Time_Stamp('/content/Karaoke-MASTER-Composition-')

print('Done!')
print('Saving to', str(fname + '.txt'))
with open(fname + '.txt', "w") as text_file:
    print(completion, file=text_file)

print('Downloading TXT file...')
from google.colab import files
files.download(fname + '.txt')

#@title Convert generated Karaoke TXT file to the Karaoke MIDI file
text_encoding = "utf_8" #@param {type:"string"}

print('Karaoke TXT to Karaoke MIDI Processor')
print('Coverting your file. Please stand-by...')




KAR_ev = 0
song_name = ''
lyrics = ''

song_name, song, lyrics, KAR_ev = TMIDI.Tegridy_Karaoke_TXT_to_MIDI_Processor(completion, text_encoding)

print('Saving your Karaoke MIDI file...')
TMIDI.Tegridy_SONG_to_MIDI_Converter(song, output_file_name=fname, output_signature='Karaoke-MASTER', track_name=song_name, text_encoding=text_encoding)
print('Downloading your Karaoke MIDI file...')
from google.colab import files
files.download(fname + '.mid')

print('Task complete! Enjoy :)')

#@title Show generated Karaoke Text
lyrics

#@title Listen to the last generated composition
#@markdown NOTE: May be very slow with the long compositions
print('Synthesizing the last output MIDI. Please stand-by... ')
FluidSynth("/usr/share/sounds/sf2/FluidR3_GM.sf2", 16000).midi_to_audio(str(fname + '.mid'), str(fname + '.wav'))
Audio(str(fname + '.wav'), rate=16000)

"""## Congrats! :) You did it :)"""