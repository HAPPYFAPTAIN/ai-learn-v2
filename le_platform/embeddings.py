import os
from fastembed import TextEmbedding
from kotaemon.base import Param
from kotaemon.embeddings import FastEmbedEmbeddings


class LocalEmbeddings(FastEmbedEmbeddings):
    @Param.auto()
    def client_(self):
        return TextEmbedding(model_name=self.model_name,threads=2,
            specific_model_path=os.environ['LE_EMBEDDING_PATH'],local_files_only=True)
