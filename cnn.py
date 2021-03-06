import numpy as np
from fc import IdentityActivator, SigmoidActivator
from math import floor


def padding(array, zero_padding):
    if array.ndim == 2:
        height = array.shape[0]
        width = array.shape[1]
        padded__array = np.zeros([height + 2 * zero_padding,
                                  width + 2 * zero_padding])
        padded__array[zero_padding: zero_padding + height, zero_padding: zero_padding + width] = array
        return padded__array
    depth = array.shape[0]
    height = array.shape[1]
    width = array.shape[2]
    padded__array = np.zeros([depth,
                              height + 2 * zero_padding,
                              width + 2 * zero_padding])
    padded__array[:, zero_padding: zero_padding + height, zero_padding: zero_padding + width] = array
    return padded__array


def element_wise_op(array, op):
    for i in np.nditer(array, op_flags=['readwrite']):
        i[...] = op(i)


def conv(input_array, output_array, filter_weights, filter_bias, stride):
    reshaped_input_array = input_array.copy()
    reshaped_filter_weights = filter_weights.copy()
    if reshaped_filter_weights.ndim == 2:
        reshaped_input_array = input_array[None, :]
    if filter_weights.ndim == 2:
        reshaped_filter_weights = filter_weights[None, :]
    for i in range(output_array.shape[0]):
        for j in range(output_array.shape[1]):
            patched_input = get_patch(reshaped_input_array, i, j, reshaped_filter_weights.shape[1], reshaped_filter_weights.shape[2], stride)
            output_array[i, j] = (patched_input * filter_weights).sum() + filter_bias


def get_patch(input_array, i, j, patch_height, patch_width, stride):
    start_i = i * stride
    start_j = j * stride
    if input_array.ndim == 2:
        return input_array[start_i: start_i + patch_height, start_j: start_j + patch_width]
    elif input_array.ndim == 3:
        return input_array[:, start_i: start_i + patch_height, start_j: start_j + patch_width]


def get_max_index(input_array):
    index_i = 0
    index_j = 0
    max_value = input_array[0, 0]
    for i in range(input_array.shape[0]):
        for j in range(input_array.shape[1]):
            if input_array[i, j] > max_value:
                max_value = input_array[i, j]
                index_i = i
                index_j = j
    return index_i, index_j


class ConvLayer(object):
    def __init__(self,
                 input_width,
                 input_height,
                 input_channel,
                 filter_width,
                 filter_height,
                 filter_number,
                 zero_padding,
                 stride,
                 input_activator,
                 output_activator,
                 learning_rate):
        self.input_width = input_width
        self.input_height = input_height
        self.input_channel = input_channel
        self.filter_width = filter_width
        self.filter_height = filter_height
        self.filer_number = filter_number
        self.zero_padding = zero_padding
        self.stride = stride
        self.input_activator = input_activator
        self.output_activator = output_activator
        self.learning_rate = learning_rate

        self.output_width = ConvLayer.calculate_output_size(input_width, filter_width, zero_padding, stride)
        self.output_height = ConvLayer.calculate_output_size(input_height, filter_height, zero_padding, stride)
        self.output = np.zeros([self.filer_number, self.output_height, self.output_width])

        self.filters = []
        for _ in range(self.filer_number):
            self.filters.append(Filter(self.filter_width, self.filter_height, self.input_channel))

    def forward(self, input_array):
        self.input_array = input_array
        self.padded_input_array = padding(self.input_array, self.zero_padding)
        for c in range(self.filer_number):
            f = self.filters[c]
            conv(self.padded_input_array, self.output[c], f.get_weights(), f.get_bias(), self.stride)
        element_wise_op(self.output, self.output_activator.forward)

    def backward(self, sensitivity_array):
        expanded_sensitivity_array = self.expand_sensitivity_map(sensitivity_array)
        zp = (self.input_width - expanded_sensitivity_array.shape[2] + self.filter_width - 1) / 2
        zp = int(floor(zp))
        padded_expanded_sensitivity_array = padding(expanded_sensitivity_array, zp)
        self.delta_array = np.zeros([self.input_channel, self.input_height, self.input_width])

        for f in range(self.filer_number):
            flipped_filter_weights = np.array(list(map(lambda i: np.rot90(i, 2), self.filters[f].get_weights())))
            delta_array = np.zeros(self.delta_array.shape)
            for i in range(self.input_channel):
                conv(padded_expanded_sensitivity_array[f], delta_array[i], flipped_filter_weights[i], 0, 1)
            self.delta_array += delta_array
        derivative_array = np.array(self.input_array)
        element_wise_op(derivative_array, self.input_activator.backward)
        self.delta_array *= derivative_array

        for f in range(self.filer_number):
            for i in range(self.input_channel):
                conv(self.padded_input_array[i], self.filters[f].w_grad[i], expanded_sensitivity_array[f], 0, 1)
            self.filters[f].b_grad = expanded_sensitivity_array[f].sum()

    def update(self, learning_rate):
        for f in range(self.filer_number):
            self.filters[f].update(learning_rate)

    def expand_sensitivity_map(self, sensitivity_array):
        height = self.calculate_output_size(self.input_height, self.filter_height, self.zero_padding, 1)
        width = self.calculate_output_size(self.input_width, self.filter_width, self.zero_padding, 1)
        expanded_array = np.zeros([self.filer_number, height, width])
        for i in range(self.output_height):
            for j in range(self.output_width):
                expanded_array[:, i * self.stride, j * self.stride] = sensitivity_array[:, i, j]
        return expanded_array

    @staticmethod
    def calculate_output_size(input_size, filter_size, zero_padding, stride):
        return int(floor((input_size + 2 * zero_padding - filter_size) / stride + 1))


class Filter(object):
    def __init__(self, width, height, depth):
        self.w = np.random.uniform(-1e-4, 1e-4, [depth, height, width])
        self.b = 0
        self.w_grad = np.zeros(self.w.shape)
        self.b_grad = 0

    def update(self, learning_rate):
        self.w -= learning_rate * self.w_grad
        self.b -= learning_rate * self.b_grad

    def get_weights(self):
        return self.w

    def get_bias(self):
        return self.b


class MaxPoolingLayer(object):
    def __init__(self, input_height, input_width, input_channel, filter_height, filter_width, stride):
        self.input_height = input_height
        self.input_width = input_width
        self.input_channel = input_channel
        self.filter_height = filter_height
        self.filter_width = filter_width
        self.stride = stride

        self.output_height = int(floor((input_height - filter_height) / stride + 1))
        self.output_width = int(floor((input_width - filter_width) / stride + 1))

        self.output = np.zeros([input_channel, self.output_height, self.output_width])

    def forward(self, input_array):
        self.input_array = input_array
        for d in range(self.input_channel):
            for i in range(self.output_height):
                for j in range(self.output_width):
                    self.output[d, i, j] = get_patch(input_array, i, j,
                                                     self.filter_height,
                                                     self.filter_width,
                                                     self.stride).max()

    def backward(self, sensitivity_array):
        self.delta_array = np.zeros([self.input_channel, self.input_height, self.input_width])
        for d in range(self.input_channel):
            for i in range(self.output_height):
                for j in range(self.output_width):
                    pathed_input_array = get_patch(self.input_array, i, j,
                                                   self.filter_height,
                                                   self.filter_width,
                                                   self.stride)
                    m, n = get_max_index(pathed_input_array)
                    self.delta_array[d, i * self.stride + m, j * self.stride + n] = sensitivity_array[d, i, j]


def check_cnn_gradient():
    input_array = np.array([1, 2, 3, 4, 5, 3, 2, 3, 4, 5, 6, 2, 34, 6, 7, 7, 8, 1, 2, 3, 4, 5, 3, 2, 3, 4, 5, 6, 6, 7, 7, 8, 34, 6, 7, 7, 8, 1, 2, 3, 4, 5, 3, 2, 3, 4, 5, 6, 7, 8])
    input_array = input_array.reshape([2, 5, 5])

    error_function = lambda x: x.sum()
    cnn1 = ConvLayer(5, 5, 2, 3, 3, 2, 1, 1, SigmoidActivator(), SigmoidActivator(), 0.001)
    cnn2 = ConvLayer(5, 5, 2, 3, 3, 1, 0, 2, SigmoidActivator(), IdentityActivator(), 0.001)
    cnn1.forward(input_array)
    cnn2.forward(cnn1.output)
    delta_array = np.ones(cnn2.output.shape)
    cnn2.backward(delta_array)
    cnn1.backward(cnn2.delta_array)

    epsilon = 0.00001
    for cnn in [cnn1, cnn2]:
        for f in range(cnn.filer_number):
            a_filter = cnn.filters[f]
            for d in range(a_filter.w.shape[0]):
                for i in range(a_filter.w.shape[1]):
                    for j in range(a_filter.w.shape[2]):
                        a_filter.w[d][i][j] += epsilon
                        cnn1.forward(input_array)
                        cnn2.forward(cnn1.output)
                        error1 = error_function(cnn2.output)
                        a_filter.w[d][i][j] -= epsilon * 2
                        cnn1.forward(input_array)
                        cnn2.forward(cnn1.output)
                        error2 = error_function(cnn2.output)
                        expected_grad = (error1 - error2) / (2 * epsilon)
                        a_filter.w[d][i][j] += epsilon
                        print('expected grad: ', expected_grad, ' actual grad: ', a_filter.w_grad[d][i][j])


if __name__ == '__main__':
    check_cnn_gradient()