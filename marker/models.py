from marker.cleaners.equations import load_nougat_model
from marker.ordering import load_ordering_model
from marker.postprocessors.editor import load_editing_model
from marker.segmentation import load_segment_model


def load_all_models():
    edit = load_editing_model()
    order = load_ordering_model()
    segment = load_segment_model()
    nougat = load_nougat_model()
    model_lst = [nougat, segment, order, edit]
    return model_lst
