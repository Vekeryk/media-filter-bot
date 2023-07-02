import numpy as np
from tensorflow import keras
import tensorflow_hub as hub

IMAGE_DIM = 224   # required/default image dimensionality
CATEGORIES = ['Drawing', 'Hentai', 'Neutral', 'Porn', 'Sexy']

def load_model():
    return keras.models.load_model("model.h5", custom_objects={'KerasLayer': hub.KerasLayer})


def classify(model, bytes_io, image_dim=IMAGE_DIM):
    images = load_image(bytes_io, (image_dim, image_dim))
    probs = classify_nd(model, images)
    return probs[0]


def load_image(bytes_io, image_size):
    image = keras.preprocessing.image.load_img(bytes_io, target_size=image_size)
    image = keras.preprocessing.image.img_to_array(image)
    image /= 255
    return np.asarray([image])


def classify_nd(model, nd_images):
    """ Classify given a model, image array (numpy)...."""
    model_preds = model.predict(nd_images)
    
    probs = []
    for _, single_preds in enumerate(model_preds):
        single_probs = {}
        for j, pred in enumerate(single_preds):
            single_probs[CATEGORIES[j]] = int(float(pred) * 100)
        probs.append(single_probs)
    return probs