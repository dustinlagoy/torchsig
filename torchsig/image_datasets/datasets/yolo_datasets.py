import numpy as np
import torch
from torch.utils.data import Dataset

"""
A class for wrapping YOLO data; contains a single datum for a YOLO dataset, with image and label data together.
This class can be treated as a tuple of (image_data, labels/class_id), and can be returned in datasets.
If no labels are provided, a class_id can be supplied, and the datum will be represented as (image_data, class_id), otherwise it will be (image_data, labels).
A YOLODatum with a class_id and no labels is assumed to have one label at [class_id, 0.5, 0.5, 1, 1].
"""
class YOLODatum():
    def __init__(self, img=None, labels=[]):
        self.img = img
        self._labels = labels
        if type(labels) is int:
            self._labels = [(labels, 0.5, 0.5, 1.0, 1.0)]
        elif type(labels) is tuple and len(labels) == 5:
            self._labels = [labels]
        elif not type(labels) is list:
            raise Exception("YOLODatum label must be an int class_id, a tuple of (class_id, cx, cy, width, height), or a list")
        
    def has_labels(self):
        return self._labels != None
    def __len__(self):
        return 2
    @property
    def labels(self):
        return self._labels
    @labels.setter
    def labels(self, new_labels):
        self._labels = YOLODatum(self.img, new_labels)._labels
    def __getitem__(self,idx):
        if self._labels != None:
            return (self.img, self._labels)[idx]
        else:
            return (self.img, self.class_id)[idx]
    def __setitem__(self, idx, new_value):
        if idx == 0:
            self.img = new_value
        elif idx == 1:
            self._labels = new_value
        else:
            raise Exception("Cannot index past 0: img or 1: labels for YOLODatum object")
    def size(self, ind):
        return self.img.size(ind)
    @property
    def shape(self):
        return self.img.shape
    """
    adds new labels to the list of labels;
    Inputs:
        new_labels: either a list of tuples to add, a single tuple of (class_id, cx, cy, width, height), or an int class_id, in which case (class_id, 0.5, 0.5, 1.0, 1.0) will be added
    """
    def append_labels(self, new_labels):
        if type(new_labels) is int:
            self._labels += [(new_labels, 0.5, 0.5, 1.0, 1.0)]
        elif type(new_labels) is list:
            self._labels += new_labels
        elif type(new_labels) is tuple:
            self._labels += [new_labels]

    """
    A function for transposing YOLO labels for boxes in one image to the appropriate labels for the same boxes in a larger composite image containing the smaller image;
    Inputs:
        yolo_datum: the pair (img1, old_labels), where img1 is the smaller image on which old_labels are accurate as a torch [n_channels, height, width] tensor
        top_left: the coordinates of the top left corner of img1 within self.img, as (x,y). such that self.img[:,y,x] is the top left corner of img1
    Outputs:
        new_labels: the new YOLO labels which describe the boxes from old_labels in self.img
    """
    def transpose_yolo_labels(self, yolo_datum, top_left):
        img1, old_labels = yolo_datum
        img2 = self.img
        new_labels = []
        img1_width, img1_height = img1.size(2), img1.size(1)
        img2_width, img2_height = img2.size(2), img2.size(1)
        for old_label in old_labels:
            class_id, old_cx, old_cy, old_width, old_height = old_label
            px_width = old_width*img1_width
            px_height = old_height*img1_height
            old_x = old_cx*img1_width
            old_y = old_cy*img1_height
            new_x = (old_x + top_left[0])
            new_y = (old_y + top_left[1])
            sx = max(0,new_x - px_width//2)
            sy = max(0,new_y - px_height//2)
            ex = min(img2_width,new_x + px_width//2)
            ey = min(img2_height,new_y + px_height//2)
            new_width = (ex - sx)/img2_width
            new_height = (ey - sy)/img2_height
            new_cx = ((ex + sx)/2)/img2_width
            new_cy = ((ey + sy)/2)/img2_height
            
            new_labels += [(class_id, new_cx, new_cy, new_width, new_height)]
        return new_labels

    """
    A function for adding YOLO labels for boxes in one image to the appropriate labels for the same boxes in a larger composite image containing the smaller image;
    automatically deletes labels for boxes which do not fall entirely inside of the larger image.
    this object will be modified to contain the labels from yolo_datum, trasposed appropriately.
    Inputs:
        yolo_datum: the pair (img1, old_labels), where img1 is the smaller image on which old_labels are accurate as a torch [n_channels, height, width] tensor
        top_left: the coordinates of the top left corner of img1 within img2, as (y,x). such that img2[:,y,x] is the top left corner of img1
    """
    def append_yolo_labels(self, yolo_datum, top_left):
        self.append_labels(self.transpose_yolo_labels(yolo_datum, top_left))

    """
    A function for composing this YOLODatum with another YOLODatum, such that the resulting image composes the two image with yolo_datum.img starting at top_left in self.img, 
        and the resulting labels contain labels from both YOLODatum objects
    Inputs:
        yolo_datum: the datum to compose into this datum
        top_left: the top left corner as (x,y) in which to append yolo_datum.img
        image_composition_mode: a string denoting the mode in which to compose the image data from the two images; either 'replace', 'max', or 'add'; 'add' by default;
    """
    def compose_yolo_data(self, yolo_datum, top_left, image_composition_mode = "add"):
        self.append_yolo_labels(yolo_datum, top_left)
        start_x, start_y = top_left
        width = min(self.img.size(2), yolo_datum.img.size(2))
        height = min(self.img.size(1), yolo_datum.img.size(1))
        if image_composition_mode == 'replace':
            self.img[:, start_y:start_y+height, start_x:start_x+width] = yolo_datum.img[:,:height,:width]
        elif image_composition_mode == 'max':
            self.img[:, start_y:start_y+height, start_x:start_x+width] = torch.max(torch.stack([self.img[:, start_y:start_y+height, start_x:start_x+width], yolo_datum.img[:,:height,:width]]), axis=0)
        elif image_composition_mode == 'add':
            self.img[:, start_y:start_y+height, start_x:start_x+width] = self.img[:, start_y:start_y+height, start_x:start_x+width] + yolo_datum.img[:,:height,:width]
        else:
            raise Exception("invalid image composition mode; must be 'max', 'add', or 'replace'")

"""
A class for adapting generic image datasets to YOLO image datasets. Expects a dataset which returns only image tensors, and a class label to apply to the dataset.
All returned data will be of the form (image_data, [(class_id, 0.5, 0.5, 1.0 1.0)]), or (image_data, []) if class_id = None
"""
class YOLODatasetAdapter(Dataset):
    def __init__(self, dataset: Dataset, class_id: int = None):
        self.dataset = dataset
        self.class_id = class_id
    def __len__(self):
        return len(self.dataset)
    def __getitem__(self, idx):
        if self.class_id == None:
            return YOLODatum(self.dataset[idx], [])
        return YOLODatum(self.dataset[idx], self.class_id)

"""
Defines a component of a composite dataset; this will contain any information the composites should use to place instances of this component in the composites, such as how many instances should be place
Inputs:
    component_dataset: a Dataset object which contains instances of this component, represented as (image_component: ndarray(c,height,width), class_id: int)
    min_to_add: the fewest instances of this component type to be placed in each composite
    max_to_add: the most instances of this type to be placed in each composite; the number of instances will be selected unifomly from min_to_add to max_to_add
    class_id: the int id to use for labeling data; 
            if provided, all returned data will be of the form (component_dataset[n], (class_id, 0.5, 0.5, 1.0, 1.0)) representing a single box taking up the full image component of class class_id
    use_source_yolo_labels: if true, load YOLO labels from the component_dataset; otherwise component_dataset is assumed to return only image tensors;

    If neither class_id nor use_source_yolo_labels is provided, all data will be assumed to have no labels, and (component_dataset[n], []) will be returned
"""
class YOLOImageCompositeDatasetComponent(Dataset):
    def __init__(self, component_dataset, min_to_add=0, max_to_add=1, class_id=None, use_source_yolo_labels=False):
        self.component_dataset = component_dataset
        self.min_to_add = min_to_add
        self.max_to_add = max_to_add
        self.class_id = class_id
        self.use_source_yolo_labels = use_source_yolo_labels
        if class_id != None:
            self.component_dataset = YOLODatasetAdapter(component_dataset, class_id)
        elif not use_source_yolo_labels:
            self.component_dataset = YOLODatasetAdapter(component_dataset, [])
    def __len__(self):
        return len(self.component_dataset)
    def __getitem__(self, idx):
        return self.component_dataset[idx]
    def next(self):
        return self.component_dataset[np.random.randint(0,len(self.component_dataset))]
    def get_components_to_add(self):
        num_to_add = np.random.randint(self.min_to_add, self.max_to_add + 1)
        to_add = []
        for i in range(num_to_add):
            to_add += [self.next()]
        return to_add

"""
A Dataset class generating synthetic composite images in yolo format from other image datasets
Inputs:
    composite_scale: a tuple of the form (height, width, num_channels) specifying the scale of the image compisites to be generated; (if a 2d tuple is passed in, it will work in greyscale)
    transforms: either a single function or list of functions from images to images to be applied to each SOI; used for adding noise and impairments to data; defaults to None
    
    <NOTE>: The dataset will not have any components to add to the composite at initialization; these must be added by calling my_instance.add_component(image_dataset_to_add)
    All components should be torch datasets which output an image in the form of an ndarray and an integer class id label as: (image_height, image_width, ?image_depth), class_id
"""
class YOLOImageCompositeDataset(Dataset):
    def __init__(self, composite_scale, transforms=None, components = [], dataset_size = 10, max_add = False):
        self.composite_scale = composite_scale
        self.transforms = transforms
        self.components = []#components # list of YOLOImageCompositeDatasetComponent objects
        self.dataset_size = dataset_size
        self.max_add = max_add
        
    def __len__(self):
        return self.dataset_size # placeholder value; this will generate new images, so there is in practice no fixed length of the dataset

    def add_component(self, component_dataset, min_to_add=0, max_to_add=1, class_id=None, use_source_yolo_labels=False):
        self.components += [YOLOImageCompositeDatasetComponent(component_dataset, min_to_add=min_to_add, max_to_add=max_to_add, class_id=class_id, use_source_yolo_labels=use_source_yolo_labels)]
        
    def get_components_to_add(self):
        to_add = []
        for component in self.components:
            to_add += component.get_components_to_add()
        return to_add

    def add_component_to_image_and_labels(self, datum, component):
        img_w = datum.img.shape[-1]
        img_h = datum.img.shape[-2]
        c_w = component.img.shape[-1]
        c_h = component.img.shape[-2]
        max_x = max(img_w - c_w, 0)
        max_y = max(img_h - c_h, 0)
        new_x = np.random.randint(0, max_x + 1)
        new_y = np.random.randint(0, max_y + 1)
        datum.compose_yolo_data(component, (new_x, new_y))
        #x_end = min(img_w, c_w + new_x)
        #y_end = min(img_h, c_h + new_y)
        #new_width = x_end - new_x
        #new_height = y_end - new_y
        #yolo_x = (new_x + new_width/2)/img_w
        #yolo_y = (new_y + new_height/2)/img_h
        #yolo_w = new_width/img_w
        #yolo_h = new_height/img_h
        #labels += [(component_label, yolo_x, yolo_y, yolo_w, yolo_h)]
        #if not self.max_add:
        #    image[:,new_y:new_y+new_height,new_x:new_x+new_width] = np.add(image[:,new_y:new_y+new_height,new_x:new_x+new_width], component_image[:,:new_height,:new_width])
        #else:
        #    image[:,new_y:new_y+new_height,new_x:new_x+new_width] = torch.max(torch.stack([image[:,new_y:new_y+new_height,new_x:new_x+new_width], component_image[:,:new_height,:new_width]], axis=0))
    
    def __getitem__(self, idx):
        full_datum = YOLODatum(torch.zeros(self.composite_scale), [])
        for component in self.get_components_to_add():
            self.add_component_to_image_and_labels(full_datum, component)
        if self.transforms:
            if type(self.transforms) == list:
                for transform in self.transforms:
                    full_datum.img = transform(full_datum.img)
            else:
                full_datum.img = self.transforms(full_datum.img)
                
        return full_datum