#!/usr/bin/env python3
"""
Knowledge Package Ingestion Script
Loads and indexes knowledge packages for ATTI agents
"""

import json
import os
import numpy as np
from pathlib import Path

class KnowledgeIngestor:
    def __init__(self, packages_dir="packages"):
        self.packages_dir = packages_dir
        self.metadata = None
        self.blocks = None
        
    def load_metadata(self):
        """Load package metadata"""
        with open("package_metadata.json", "r") as f:
            self.metadata = json.load(f)
        print(f"✅ Metadata loaded: {len(self.metadata['packages'])} packages")
        
    def load_blocks(self):
        """Load knowledge blocks"""
        with open("knowledge_blocks.json", "r") as f:
            self.blocks = json.load(f)
        print(f"✅ Blocks loaded: {len(self.blocks['blocks'])} blocks")
        
    def validate_structure(self):
        """Validate package structure"""
        errors = []
        
        for package in self.metadata["packages"]:
            pkg_dir = Path(self.packages_dir) / package["id"]
            if not pkg_dir.exists():
                errors.append(f"Missing directory: {pkg_dir}")
                
        if errors:
            print("❌ Validation errors:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        print("✅ Structure validated")
        return True
        
    def create_embeddings(self):
        """Create sample embeddings (placeholder)"""
        total_embeddings = self.metadata["total_embeddings"]
        embedding_dim = self.metadata["embedding_dimension"]
        
        embeddings = np.random.randn(total_embeddings, embedding_dim).astype(np.float32)
        
        indices_dir = Path("indices")
        indices_dir.mkdir(exist_ok=True)
        
        embeddings_dir = Path("embeddings")
        embeddings_dir.mkdir(exist_ok=True)
        
        np.save(embeddings_dir / "atti_embeddings.npy", embeddings)
        print(f"✅ Embeddings created: {embeddings.shape}")
        
    def index_with_faiss(self):
        """Index embeddings with FAISS"""
        try:
            import faiss
            
            embeddings = np.load("embeddings/atti_embeddings.npy")
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)
            
            faiss.write_index(index, "indices/atti_tax_knowledge_faiss.bin")
            print(f"✅ FAISS index created: {index.ntotal} vectors")
            
        except ImportError:
            print("⚠️  FAISS not available, skipping indexing")
            
    def run(self):
        """Execute full ingestion pipeline"""
        print("🔄 Starting knowledge ingestion...")
        
        self.load_metadata()
        self.load_blocks()
        
        if not self.validate_structure():
            return False
            
        self.create_embeddings()
        self.index_with_faiss()
        
        print("✅ Ingestion complete!")
        return True

if __name__ == "__main__":
    ingestor = KnowledgeIngestor()
    ingestor.run()
