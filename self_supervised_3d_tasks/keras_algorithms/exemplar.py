import numpy as np

from self_supervised_3d_tasks.custom_preprocessing.preprocessing_exemplar import preprocessing_exemplar
from self_supervised_3d_tasks.keras_algorithms.custom_utils import apply_encoder_model_3d, apply_encoder_model

from tensorflow.keras.layers import Concatenate, Lambda, Flatten, Input
import tensorflow.python.keras.backend as K
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.models import load_model, Model, Sequential


class ExemplarBuilder:
    def __init__(
            self,
            dim=384,
            number_channels=3,
            batch_size=10,
            dim_3d=False,
            alpha_triplet=0.2,
            embedding_size=10,
            lr=0.0006,
            model_checkpoint=None,
            **kwargs
    ):
        self.number_channels = number_channels
        self.batch_size = batch_size
        self.dim_3d = dim_3d
        self.dim = (dim, dim, dim) if self.dim_3d else (dim, dim)
        self.alpha_triplet = alpha_triplet
        self.embedding_size = embedding_size
        self.lr = lr
        self.model_checkpoint = model_checkpoint
        self.kwargs = kwargs

    def triplet_loss(self, y_true, y_pred, _alpha=.5):
        """
        This function returns the calculated triplet loss for y_pred
        :param y_true: not needed
        :param y_pred: predictions of the model
        :param embedding_size: length of embedding
        :param _alpha: defines the shift of the loss
        :return: calculated loss
        """
        embeddings = K.reshape(y_pred, (-1, 3, self.embedding_size))

        positive_distance = K.mean(K.square(embeddings[:, 0] - embeddings[:, 1]), axis=-1)
        negative_distance = K.mean(K.square(embeddings[:, 0] - embeddings[:, 2]), axis=-1)
        return K.mean(K.maximum(0.0, positive_distance - negative_distance + _alpha))

    def apply_model(self, input_shape, **kwargs):
        """
        apply model function to apply the model
        :param input_shape: defines the input shape (dim last)
        :param embedding_size: number of embedded layers
        :param lr: learning rate
        :return: return the network (encoder) and the compiled model with concated output
        """
        # defines encoder
        if self.dim_3d:
            network = apply_encoder_model_3d((*self.dim, self.number_channels), self.embedding_size, **self.kwargs)
        else:
            network = apply_encoder_model((*self.dim, self.number_channels), self.embedding_size, **self.kwargs)

        # Define the tensors for the three input images

        input = Input((3, *input_shape), name="Input")
        anchor_input = Lambda(lambda x: x[:, 0, :], name="anchor_input")(input)
        positive_input = Lambda(lambda x: x[:, 1, :], name="positive_input")(input)
        negative_input = Lambda(lambda x: x[:, 2, :], name="negative_input")(input)

        # Generate the encodings (feature vectors) for the three images
        encoded_a = Sequential(network, name="encoder_a")(anchor_input)
        encoded_p = Sequential(network, name="encoder_p")(positive_input)
        encoded_n = Sequential(network, name="encoder_n")(negative_input)

        # Concat the outputs together
        output = Concatenate()([encoded_a, encoded_p, encoded_n])

        # set optimizer
        optimizer = Adam(lr=self.lr)

        # Connect the inputs with the outputs
        model = Model(inputs=input, outputs=output)
        print(network.summary())
        # compile the model
        model.compile(loss=self.triplet_loss, optimizer=optimizer)
        return network, model

    def get_training_model(self):
        return self.apply_model((*self.dim, self.number_channels))[1]

    def get_training_preprocessing(self):
        def f_train(x, y):
            return preprocessing_exemplar(x, y, self.dim_3d)

        def f_val(x, y):
            return preprocessing_exemplar(x, y, self.dim_3d)

        return f_train, f_val

    def get_finetuning_preprocessing(self):
        def f_train(x, y):
            return preprocessing_exemplar(x, y, self.dim_3d)

        def f_val(x, y):
            return preprocessing_exemplar(x, y, self.dim_3d)

        return f_train, f_val

    def get_finetuning_layers(self, load_weights, freeze_weights):
        enc_model, model_full = self.apply_model((*self.dim, self.number_channels))

        if load_weights:
            model_full.load_weights(self.model_checkpoint)

        if freeze_weights:
            # freeze the encoder weights
            enc_model.trainable = False

        layer_in = Input((*self.dim, self.number_channels), name="anchor_input")
        layer_out = Sequential(enc_model)(layer_in)

        x = Flatten()(layer_out)
        return layer_in, x, [enc_model, model_full]


def create_instance(*params, **kwargs):
    return ExemplarBuilder(*params, **kwargs)
