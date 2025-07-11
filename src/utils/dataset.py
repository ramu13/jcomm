import os
import random
import numpy as np
import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence


# FIXME: toy_flag は使われていないので削除するか検討
class CommutingODDataset(Dataset):
    """
    1つの area (= フォルダ) を 1サンプルとみなし、
    x: (N, N, F)   y: (N, N)  を返す Dataset
    """
    def __init__(self, root, areas, toy_flag=False):
        self.root = root
        self.areas = areas.copy()
        self.toy_flag = toy_flag

    def __len__(self):
        return len(self.areas)

    def _load_area_arrays(self, area):
        prefix = os.path.join(self.root, area)
        demos = np.load(f"{prefix}/demos.npy") # shape (N, F_d)
        pois  = np.load(f"{prefix}/pois.npy")  # shape (N, F_p)
        dis   = np.load(f"{prefix}/dis.npy")   # shape (N, N)
        od    = np.load(f"{prefix}/od.npy")    # shape (N, N)
        return demos, pois, dis, od

    def _make_feature_tensor(self, demos, pois, dis):
        feat = np.concatenate([demos, pois], axis=1) # (N, F_d+F_p)
        N, F = feat.shape

        # ブロードキャスト展開（メモリ効率版）
        feat_o = feat[:, None, :] # (N, 1, F)
        feat_d = feat[None, :, :] # (1, N, F)
        dis    = dis[..., None]   # (N, N, 1)

        x = np.concatenate([np.repeat(feat_o, N, axis=1), # (N, N, F)
                            np.repeat(feat_d, N, axis=0), # (N, N, F)
                            dis], axis=2)                 # (N, N, 1)

        return torch.from_numpy(x).float()  # (N, N, 2F+1)

    def __getitem__(self, idx):
        area = self.areas[idx]
        demos, pois, dis, od = self._load_area_arrays(area)
        x = self._make_feature_tensor(demos, pois, dis)        # (N, N, 2F+1)
        y = torch.from_numpy(od).float()                       # (N, N)
        return {"x": x, "y": y, "area": area}



class CommutingODPairDataset(torch.utils.data.Dataset):
    """
        1つの area (= フォルダ) 内の地点間ペアをサンプルとする Dataset
        x: (F,)  y: scalar
        各地点間のペア (i, j) がひとつのサンプルを形成します。
    """
    def __init__(self, root, areas, toy_flag=False):
        self.root = root
        self.areas = areas.copy()
        self.toy_flag = toy_flag

        self.samples = []
        for area in self.areas:
            demos, pois, dis, od = self._load_area_arrays(area)
            x = self._make_feature_tensor(demos, pois, dis)  # (N,N,F)
            y = od                                           # (N,N)
            N = x.shape[0]

            for i in range(N):
                for j in range(N):
                    y_ij = y[i, j]
                    self.samples.append({
                        "x": x[i, j],                   # shape (F,)
                        "y": torch.tensor(y_ij).float(),# scalar
                        "area": area,
                        "i": i,
                        "j": j
                    })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        return {
            "x": s["x"],     # Tensor(F,)
            "y": s["y"],     # scalar
            "area": s["area"],
            "i": s["i"],
            "j": s["j"]
        }

    def _load_area_arrays(self, area):
        prefix = os.path.join(self.root, area)
        demos = np.load(f"{prefix}/demos.npy")     # (N, D_d)
        pois  = np.load(f"{prefix}/pois.npy")      # (N, D_p)
        dis   = np.load(f"{prefix}/dis.npy")       # (N, N)
        od    = np.load(f"{prefix}/od.npy")        # (N, N)
        return demos, pois, dis, od

    def _make_feature_tensor(self, demos, pois, dis):
        """
            特徴量テンソルを作成する関数
            :param demos: (N, D_d)  各地点の人口情報
            :param pois: (N, D_p)   各地点のPOI情報
            :param dis: (N, N)     各地点間の距離行列
            :return: (N, N, F)     特徴量テンソル
        """
        # 総人口情報のみを用いる場合
        if self.toy_flag:
            feat = demos[:, [0]] # (N,1)
        else: # 調査情報全てとPOIも用いる場合
            feat = np.concatenate([demos, pois], axis=1) # (N,F) 
            
        N = feat.shape[0]
        feat_o = feat[:, None, :]                      # (N,1,F)
        feat_d = feat[None, :, :]                      # (1,N,F)
        dis    = dis[..., None]                        # (N,N,1)
        x = np.concatenate([np.repeat(feat_o, N, axis=1),
                            np.repeat(feat_d, N, axis=0),
                            dis], axis=2)              # (N,N,2F+1)
        return torch.from_numpy(x).float()             # (N,N,F)