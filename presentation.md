# Clustering: Beyond KMeans — Notebook Generation Prompt

> **Purpose:** This document serves as a comprehensive prompt for an AI agent (Claude) to generate an executable Jupyter notebook demonstrating clustering algorithms with animated visualizations.

---

## GENERATION INSTRUCTIONS

### Target Output
Generate a single Jupyter notebook (`clustering_comprehensive.ipynb`) containing:
- **Markdown cells** for conceptual explanations (one per topic)
- **Python code cells** that are fully executable and produce visualizations
- **Animated GIFs** as primary output for algorithm demonstrations
- **Static plots** for comparison and evaluation sections

### Required Libraries
```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from PIL import Image
import io
from IPython.display import Image as IPImage, display

# Scikit-learn - Clustering
from sklearn.datasets import make_blobs, make_moons, make_circles, make_swiss_roll
from sklearn.cluster import KMeans, DBSCAN, OPTICS, SpectralClustering, AgglomerativeClustering
from sklearn.mixture import GaussianMixture

# Scikit-learn - Preprocessing & Reduction
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE, Isomap

# Scikit-learn - Evaluation
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.metrics import adjusted_rand_score, v_measure_score

# Scikit-learn - Utilities
from sklearn.neighbors import kneighbors_graph
from scipy.cluster.hierarchy import dendrogram, linkage

import warnings
warnings.filterwarnings('ignore')
```

### Global Visual Style Constants
**CRITICAL:** Use these consistently across ALL visualizations for professional coherence.

```python
# =============================================================================
# GLOBAL CONSTANTS - Use these in every visualization
# =============================================================================
RANDOM_STATE = 170

# Figure sizes
FIGURE_SIZE_SINGLE = (7, 6)
FIGURE_SIZE_WIDE = (10, 5)
FIGURE_SIZE_GRID_2x2 = (12, 11)
FIGURE_SIZE_GRID_3x2 = (14, 10)

# GIF parameters
GIF_DURATION_MS = 600
GIF_PAUSE_FRAMES = 4  # Extra frames at convergence for pause effect

# Color palettes (5 colors for up to 5 clusters)
REGION_COLORS = ['#F08080', '#90EE90', '#87CEEB', '#DDA0DD', '#F0E68C']
POINT_COLORS = ['#DC143C', '#228B22', '#4682B4', '#8B008B', '#DAA520']
NOISE_COLOR = '#808080'  # Gray for DBSCAN noise points

# Centroid marker style (white circle with black cross = ⊕)
def plot_centroid(ax, x, y):
    """Plot a centroid with consistent style."""
    ax.scatter(x, y, c='white', marker='o', s=280, 
               edgecolors='black', linewidths=2.5, zorder=10)
    ax.scatter(x, y, c='black', marker='+', s=180, 
               linewidths=2.5, zorder=11)

def plot_centroids(ax, centers):
    """Plot multiple centroids."""
    for center in centers:
        plot_centroid(ax, center[0], center[1])
```

### GIF Generation Utilities
```python
# =============================================================================
# GIF GENERATION UTILITIES
# =============================================================================

def setup_transparent_figure(figsize=FIGURE_SIZE_SINGLE):
    """Create figure with transparent background."""
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    return fig, ax

def fig_to_pil(fig):
    """Convert matplotlib figure to PIL Image with transparency."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, transparent=True)
    buf.seek(0)
    img = Image.open(buf).convert('RGBA')
    plt.close(fig)
    buf.close()
    return img

def convert_to_gif_frame(img):
    """Convert RGBA image to palette mode with transparency for GIF."""
    alpha = img.split()[3]
    img_p = img.convert('P', palette=Image.ADAPTIVE, colors=255)
    mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
    img_p.paste(255, mask)
    return img_p

def save_animation(frames, output_path, duration=GIF_DURATION_MS):
    """Save list of PIL Images as animated GIF with transparency."""
    gif_frames = [convert_to_gif_frame(f) for f in frames]
    gif_frames[0].save(
        output_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration,
        loop=0,
        transparency=255,
        disposal=2  # Clear frame before drawing next (prevents ghosting)
    )
    print(f"✓ Saved: {output_path} ({len(frames)} frames)")
    display(IPImage(filename=output_path))
    return output_path

def draw_voronoi_regions(ax, centers, xlim, ylim, colors=REGION_COLORS, resolution=300):
    """Draw Voronoi-style decision boundary regions."""
    xx, yy = np.meshgrid(
        np.linspace(xlim[0], xlim[1], resolution),
        np.linspace(ylim[0], ylim[1], resolution)
    )
    grid_points = np.c_[xx.ravel(), yy.ravel()]
    
    # Assign each grid point to nearest centroid
    distances = np.sqrt(((grid_points[:, np.newaxis] - centers) ** 2).sum(axis=2))
    labels = np.argmin(distances, axis=1).reshape(xx.shape)
    
    n_clusters = len(centers)
    ax.contourf(xx, yy, labels, 
                levels=np.arange(-0.5, n_clusters + 0.5, 1),
                colors=colors[:n_clusters], alpha=0.75)
```

---

## NOTEBOOK SECTIONS

Each section below specifies the exact content for markdown and code cells.

---

## Section 1: Title & Setup

### Cell 1 (Markdown):
```markdown
# Clustering: Beyond KMeans
### Practical Algorithms for Complex Geometries and High Dimensions

This notebook demonstrates clustering algorithms through **animated visualizations**. 

**Structure:**
1. **KMeans Baseline** — Lloyd's Algorithm animated
2. **Failure Modes** — When assumptions break
3. **Solutions** — GMM, proper K selection
4. **Alternative Algorithms** — DBSCAN, Spectral, Hierarchical
5. **Evaluation** — How to measure cluster quality

**Core Insight:** There is no "best" clustering algorithm. Your algorithm choice is a **hypothesis about your data's geometry**.
```

### Cell 2 (Code): Setup
```python
# =============================================================================
# SETUP: Imports and Global Configuration
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from PIL import Image
import io
from IPython.display import Image as IPImage, display

from sklearn.datasets import make_blobs, make_moons, make_circles, make_swiss_roll
from sklearn.cluster import KMeans, DBSCAN, OPTICS, SpectralClustering, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE, Isomap
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.metrics import adjusted_rand_score, v_measure_score
from sklearn.neighbors import kneighbors_graph
from scipy.cluster.hierarchy import dendrogram, linkage

import warnings
warnings.filterwarnings('ignore')

# [INSERT ALL GLOBAL CONSTANTS FROM ABOVE]
# [INSERT ALL UTILITY FUNCTIONS FROM ABOVE]

print("✓ Setup complete. All libraries loaded.")
```

---

## Section 2: KMeans — Lloyd's Algorithm Animation

### Cell 3 (Markdown):
```markdown
# KMeans: The Baseline Algorithm

KMeans is the most common starting point for clustering. It minimizes **Inertia** (within-cluster sum of squares) via **Lloyd's Algorithm**:

## The Iterative Process:
1. **Initialize:** Randomly place K centroids
2. **Assign:** Each point → nearest centroid (Voronoi partition)
3. **Update:** Centroid → mean of assigned points
4. **Repeat:** Until convergence (centroids stop moving)

## Key Factors:
- **Initial centroids:** Use `k-means++` for smart initialization
- **Number of clusters K:** Critical choice (see later section)
- **Distance metric:** Euclidean by default (assumes spherical clusters)

The animation below shows Lloyd's Algorithm converging. Watch how:
- Decision boundaries (colored regions) shift each iteration
- Centroids (⊕) migrate toward true cluster centers
```

### Cell 4 (Code): Lloyd's Algorithm Animation
**Task:** Generate animated GIF showing KMeans convergence with Voronoi boundaries.

**Data Specification:**
```python
# Well-separated clusters for clear demonstration
np.random.seed(42)
n_points = 80

cluster1 = np.random.randn(n_points, 2) * 0.7 + [1.5, 3.0]   # Red - left
cluster2 = np.random.randn(n_points, 2) * 0.6 + [6.5, 2.0]   # Green - bottom right  
cluster3 = np.random.randn(n_points, 2) * 0.5 + [7.0, 4.8]   # Blue - top right

X_demo = np.vstack([cluster1, cluster2, cluster3])
```

**Algorithm Specification:**
- Initialize centroids FAR from true centers: `[[7.5, 5.5], [1.0, 1.0], [4.0, 4.0]]`
- Use `momentum = 0.4` for slow convergence (shows more iterations)
- Maximum 20 iterations
- Add 4 pause frames at convergence

**Visualization:**
- Voronoi decision boundaries as colored regions
- Points colored by current cluster assignment
- Centroids as white circle + black cross (⊕)
- Title: `"Iteration number {i}"`
- Axis limits: `xlim=(-0.5, 9)`, `ylim=(-0.5, 6)`

**Output:** `kmeans_animation.gif`

---

## Section 3: KMeans Failure Modes

### Cell 5 (Markdown):
```markdown
# K-Means Failure Modes

KMeans makes **strong geometric assumptions**:
1. Clusters are **spherical** (isotropic)
2. Clusters have **equal variance** (spread)
3. Clusters are **similar in size**

When data violates these assumptions, KMeans produces meaningless results:

| Failure Mode | Assumption Violated | What Goes Wrong |
|--------------|---------------------|-----------------|
| **Wrong K** | Unknown structure | Arbitrary splits or merges |
| **Anisotropic Blobs** | Spherical clusters | Elongated shapes get split |
| **Unequal Variance** | Equal spread | Large clusters split, small absorbed |
| **Uneven Sizes** | Similar sizes | Large clusters dominate centroid placement |

The animation shows all 4 failure modes simultaneously.
```

### Cell 6 (Code): Failure Modes Animation
**Task:** Generate 2x2 grid animation showing 4 failure scenarios.

**Data Specification (from sklearn examples):**
```python
n_samples = 1500
random_state = 170
transformation = [[0.60834549, -0.63667341], [-0.40887718, 0.85253229]]

# Generate base blobs
X_base, y_base = make_blobs(n_samples=n_samples, random_state=random_state)

# Scenario 1: Standard blobs with WRONG K
X_wrong_k = X_base.copy()

# Scenario 2: Anisotropic (elongated) blobs
X_aniso = np.dot(X_base, transformation)

# Scenario 3: Unequal variance
X_varied, _ = make_blobs(n_samples=n_samples, cluster_std=[1.0, 2.5, 0.5], 
                         random_state=random_state)

# Scenario 4: Uneven sizes (500 + 100 + 10 points)
X_uneven = np.vstack([
    X_base[y_base == 0][:500],
    X_base[y_base == 1][:100],
    X_base[y_base == 2][:10]
])
```

**Scenarios Table:**
| Index | Data | K | Title |
|-------|------|---|-------|
| 0 | `X_wrong_k` | 2 | "Non-optimal Number of Clusters" |
| 1 | `X_aniso` | 3 | "Anisotropically Distributed Blobs" |
| 2 | `X_varied` | 3 | "Unequal Variance" |
| 3 | `X_uneven` | 3 | "Unevenly Sized Blobs" |

**Animation Requirements:**
- Step through KMeans using `max_iter=1` trick (reinitialize with current centers)
- Show centroids on each frame
- Title format: `"{scenario_title}\nIteration {i}"`

**Output Files:**
- Individual: `kmeans_failure_0.gif`, `kmeans_failure_1.gif`, etc.
- Combined: `kmeans_failure_modes_combined.gif`

---

## Section 4: Solutions to KMeans Failures

### Cell 7 (Markdown):
```markdown
# Solutions to K-Means Failures

Each failure mode has a corresponding solution:

| Failure | Solution | Why It Works |
|---------|----------|--------------|
| **Wrong K** | Use correct K=3 | Data-driven K selection (see next section) |
| **Anisotropic** | **Gaussian Mixture Model (GMM)** | Models elliptical covariance per cluster |
| **Unequal Variance** | **GMM** | Each cluster has own variance parameters |
| **Uneven Sizes** | **n_init=10** | Multiple random starts find small clusters |

## Key Insight: GMM as Natural Extension of KMeans

- KMeans: **Hard** assignment (point belongs to exactly one cluster)
- GMM: **Soft** assignment (point has probability of belonging to each cluster)
- GMM models **full covariance** → can fit ellipses, not just circles
```

### Cell 8 (Code): Solutions Animation
**Task:** Generate 2x2 grid animation showing solutions to each failure mode.

**Solutions Specification:**
| Index | Data | Model | Parameters | Title |
|-------|------|-------|------------|-------|
| 0 | `X_wrong_k` | KMeans | `n_clusters=3` | "Optimal Number of Clusters" |
| 1 | `X_aniso` | GMM | `n_components=3` | "Anisotropically Distributed Blobs\n(Gaussian Mixture)" |
| 2 | `X_varied` | GMM | `n_components=3` | "Unequal Variance\n(Gaussian Mixture)" |
| 3 | `X_uneven` | KMeans | `n_clusters=3, n_init=10` | "Unevenly Sized Blobs\n(n_init=10)" |

**GMM Animation:**
- Show iterations: `[1, 2, 3, 5, 8, 12, 20, 50, 100]`
- Display GMM means as centroids

**Output:** `kmeans_solutions_combined.gif`

---

## Section 5: Estimating K

### Cell 9 (Markdown):
```markdown
# Estimating the Number of Clusters (K)

One of the hardest problems in clustering. Common methods:

| Method | Metric | Decision Rule | Caveat |
|--------|--------|---------------|--------|
| **Elbow** | SSE (Inertia) | Look for "elbow" | Often ambiguous |
| **Silhouette** | Cohesion vs Separation | Maximize | Biased toward convex |
| **Calinski-Harabasz** | Between/Within variance | Maximize | Assumes spherical |
| **Gap Statistic** | vs. Null distribution | Statistical test | Computationally expensive |

## Practical Guidance:
1. Use **Elbow + Silhouette** for quick exploration
2. Use **Gap Statistic** when rigor matters
3. **Always validate with domain expertise** — if K=7 makes no business sense, it's wrong
```

### Cell 10 (Code): K Selection Methods
**Task:** Generate comparison plots for K selection methods.

**Data:**
```python
# Clear case: 4 well-separated clusters
X_clear, y_clear = make_blobs(n_samples=500, centers=4, cluster_std=0.8, random_state=42)

# Ambiguous case: 4 overlapping clusters  
X_ambig, y_ambig = make_blobs(n_samples=500, centers=4, cluster_std=2.0, random_state=42)
```

**Visualization (2x2 grid):**
1. Top-left: Elbow plot (clear data) — SSE vs K
2. Top-right: Elbow plot (ambiguous data) — show ambiguous elbow
3. Bottom-left: Silhouette plot (clear data)
4. Bottom-right: Silhouette plot (ambiguous data)

**Output:** `k_selection_comparison.png`

---

## Section 6: Dimensionality Reduction — PCA

### Cell 11 (Markdown):
```markdown
# Dimensionality Reduction: PCA

## The Curse of Dimensionality
In high dimensions (D > 50), Euclidean distance becomes meaningless:
- All points appear roughly equidistant
- KMeans centroids become unstable
- Noise dominates signal

## PCA Solution
**Principal Component Analysis** projects data onto axes that maximize variance:
- Reduces noise by discarding low-variance dimensions
- Stabilizes distance metrics for KMeans
- Rule of thumb: Keep components explaining 90-95% variance

## When to Use:
- Before KMeans on data with >50 features
- When you suspect redundant/correlated features
- For visualization (reduce to 2-3D)
```

### Cell 12 (Code): PCA Demonstration
**Task:** Show clustering improvement after PCA.

**Data:**
```python
# High-dimensional data (50 features, 5 true clusters)
X_high, y_true = make_blobs(n_samples=500, n_features=50, centers=5, 
                            cluster_std=2.0, random_state=42)
```

**Process:**
1. Cluster original 50D data with KMeans
2. Apply PCA (keep 10 components)
3. Cluster PCA-reduced data with KMeans
4. Compare silhouette scores

**Visualization (1x3):**
1. t-SNE of original, colored by KMeans labels
2. t-SNE of PCA-reduced, colored by KMeans labels
3. Bar chart comparing silhouette scores

**Output:** `pca_improvement.png`

---

## Section 7: Manifold Learning — Swiss Roll

### Cell 13 (Markdown):
```markdown
# Manifold Learning: Unfolding Complex Geometry

## The Manifold Hypothesis
Real-world high-dimensional data often lies on a **lower-dimensional curved surface** (manifold) embedded in the high-dimensional space.

**Example:** Images of faces vary along a few dimensions (pose, lighting) despite having millions of pixels.

## Methods:

| Method | Approach | Best For |
|--------|----------|----------|
| **ISOMAP** | Geodesic (along-surface) distance | Unfolding global structure |
| **t-SNE** | Preserve local neighborhoods | Visualization only |
| **UMAP** | Faster t-SNE alternative | Visualization only |

## ⚠️ Warning
**Never cluster directly on t-SNE/UMAP output!** They distort densities and distances. Use them for visualization, not as clustering input.
```

### Cell 14 (Code): Swiss Roll Demonstration
**Task:** Compare PCA vs ISOMAP vs t-SNE on Swiss Roll.

**Data:**
```python
X_swiss, color_swiss = make_swiss_roll(n_samples=1500, noise=0.5, random_state=42)
```

**Visualization (2x2):**
1. 3D Swiss Roll (colored by position along roll)
2. PCA projection → 2D (fails — folds overlap)
3. ISOMAP projection → 2D (succeeds — unrolls correctly)
4. t-SNE projection → 2D (preserves local, distorts global)

**Output:** `manifold_swiss_roll.png`

---

## Section 8: Spectral Clustering

### Cell 15 (Markdown):
```markdown
# Spectral Clustering: Graph-Based Partitioning

## When KMeans Fails
KMeans cannot handle **non-convex** shapes (rings, crescents, interleaved spirals) because it clusters by distance to centroids.

## Spectral Clustering Mechanism
1. **Similarity Graph:** Points are nodes; edges weighted by similarity (e.g., Gaussian kernel)
2. **Graph Laplacian:** Compute L = D - W (degree matrix minus adjacency)
3. **Eigen-decomposition:** Extract top K eigenvectors of L
4. **Clustering:** Apply KMeans on eigenvectors (not original features!)

## Why It Works
Eigenvectors of the Laplacian encode **connectivity** structure. Points in the same connected component have similar eigenvector values, even if far apart in Euclidean space.

## ⚠️ Scalability Warning
Eigenvalue decomposition is O(N³). Use only for datasets < 10K points.
```

### Cell 16 (Code): Spectral vs KMeans on Circles
**Task:** Side-by-side comparison on concentric circles.

**Data:**
```python
X_circles, y_circles = make_circles(n_samples=1000, factor=0.5, noise=0.05, random_state=42)
```

**Algorithms:**
- KMeans (n_clusters=2)
- SpectralClustering (n_clusters=2, affinity='nearest_neighbors')

**Visualization (1x2):**
1. Left: KMeans result (fails — splits circles incorrectly)
2. Right: Spectral result (succeeds — finds inner/outer rings)

**Output:** `spectral_vs_kmeans_circles.png`

---

## Section 9: DBSCAN — Density-Based Clustering

### Cell 17 (Markdown):
```markdown
# DBSCAN: Density-Based Clustering

## Core Idea
A cluster is a **dense region** of points separated from other dense regions by **sparse regions**.

## Parameters
- `eps` (ε): Radius of neighborhood
- `min_samples`: Minimum points to form a "core point"

## How It Works
1. Find **core points** (≥ min_samples neighbors within eps)
2. Connect core points that are neighbors → clusters
3. Assign non-core points to nearest cluster
4. Points with no cluster = **noise** (label = -1)

## Advantages Over KMeans
| Feature | KMeans | DBSCAN |
|---------|--------|--------|
| K required? | Yes | No (discovered) |
| Shape | Spherical only | Arbitrary |
| Noise handling | Forced into clusters | Explicit noise label |

## Limitation
Single `eps` value fails when cluster **densities vary** significantly.
```

### Cell 18 (Code): DBSCAN with Noise
**Task:** Show DBSCAN handling arbitrary shapes + noise.

**Data:**
```python
# Moons with added noise
X_moons, _ = make_moons(n_samples=500, noise=0.1, random_state=42)
noise_points = np.random.uniform(low=-1.5, high=2.5, size=(50, 2))
X_noisy_moons = np.vstack([X_moons, noise_points])
```

**Algorithms:**
- KMeans (n_clusters=2)
- DBSCAN (eps=0.2, min_samples=5)

**Visualization (1x2):**
1. KMeans: Forces noise into clusters
2. DBSCAN: Correctly labels noise as gray points

**Output:** `dbscan_noise_handling.png`

---

## Section 10: OPTICS — Variable Density

### Cell 19 (Markdown):
```markdown
# OPTICS: Handling Variable Density

## The Problem with DBSCAN
A single `eps` value cannot handle clusters with different densities:
- Too small → misses sparse clusters
- Too large → merges dense clusters

## OPTICS Solution
**Ordering Points To Identify Clustering Structure** considers **multiple epsilon values** simultaneously.

## Output: Reachability Plot
- X-axis: Points in cluster order
- Y-axis: Reachability distance (how far to reach this point)
- **Valleys** = Clusters
- **Depth** = Density (deeper = denser)

Think of it as a **topographic map** of cluster density.
```

### Cell 20 (Code): OPTICS Reachability Plot
**Task:** Compare DBSCAN vs OPTICS on variable-density data.

**Data:**
```python
np.random.seed(42)
# Dense cluster
dense_cluster = np.random.randn(300, 2) * 0.3 + [0, 0]
# Sparse cluster
sparse_cluster = np.random.randn(300, 2) * 1.5 + [5, 5]
# Medium cluster
medium_cluster = np.random.randn(200, 2) * 0.7 + [2.5, 5]

X_varying = np.vstack([dense_cluster, sparse_cluster, medium_cluster])
```

**Visualization (2 rows):**
- Top row (1x2): Scatter plots colored by DBSCAN vs OPTICS labels
- Bottom row: OPTICS reachability plot with cluster valleys marked

**Output:** `optics_reachability.png`

---

## Section 11: Hierarchical Clustering

### Cell 21 (Markdown):
```markdown
# Hierarchical Clustering: Dendrograms

## Agglomerative (Bottom-Up) Approach
1. Start: Each point is its own cluster
2. Merge: Combine two closest clusters
3. Repeat: Until single cluster remains
4. Output: **Dendrogram** (tree of merges)

## Linkage Methods
How to measure "distance" between clusters:

| Linkage | Definition | Cluster Shape |
|---------|------------|---------------|
| **Ward** | Minimize within-cluster variance | Spherical |
| **Single** | Minimum pairwise distance | Chains/elongated |
| **Complete** | Maximum pairwise distance | Compact |
| **Average** | Mean pairwise distance | Balanced |

## The "Superpower": Connectivity Constraints
Pass a **connectivity matrix** to restrict which points can merge:
- Only merge **spatially adjacent** points
- Reduces complexity from O(N³) to near-linear
- Essential for **image segmentation** and **time-series**
```

### Cell 22 (Code): Dendrogram Comparison
**Task:** Show dendrograms with different linkage methods.

**Data:**
```python
X_hier, _ = make_blobs(n_samples=50, centers=3, cluster_std=1.0, random_state=42)
```

**Visualization (2x2):**
- 4 dendrograms: Ward, Single, Complete, Average
- Draw horizontal line showing cut for 3 clusters
- Title showing linkage method

**Output:** `hierarchical_linkage_comparison.png`

---

## Section 12: Evaluation Metrics

### Cell 23 (Markdown):
```markdown
# Clustering Evaluation Metrics

## External Metrics (Ground Truth Available)

| Metric | Range | Interpretation |
|--------|-------|----------------|
| **Adjusted Rand Index (ARI)** | [-1, 1] | 0 = random, 1 = perfect |
| **V-Measure** | [0, 1] | Harmonic mean of homogeneity & completeness |

## Internal Metrics (No Ground Truth)

| Metric | Range | Interpretation | Bias |
|--------|-------|----------------|------|
| **Silhouette** | [-1, 1] | Higher = better separated | Convex clusters |
| **Calinski-Harabasz** | [0, ∞) | Higher = better | Convex clusters |
| **Davies-Bouldin** | [0, ∞) | Lower = better | Convex clusters |

## ⚠️ Critical Warning
Internal metrics are **biased toward convex (spherical) clusters**. They will:
- Penalize correct DBSCAN results on ring-shaped data
- Prefer KMeans even when Spectral is correct

**Always combine metrics with visual inspection and domain expertise.**
```

### Cell 24 (Code): Metrics Comparison
**Task:** Compare metrics across algorithms on same data.

**Data:**
```python
# Moons dataset (non-convex ground truth)
X_eval, y_true = make_moons(n_samples=500, noise=0.1, random_state=42)
```

**Algorithms:**
- KMeans (n_clusters=2)
- SpectralClustering (n_clusters=2)
- DBSCAN (eps=0.2, min_samples=5)

**Metrics to compute:**
- ARI (external)
- V-Measure (external)
- Silhouette (internal)
- Calinski-Harabasz (internal)
- Davies-Bouldin (internal)

**Output:** 
1. Table of all metrics
2. Bar chart visualization
3. Comment on metric biases

---

## Section 13: Algorithm Comparison Summary

### Cell 25 (Markdown):
```markdown
# Algorithm Selection Decision Tree

```
START: What do you know about your data?
│
├─► Is K (number of clusters) known?
│   │
│   ├─► YES: Are clusters spherical & equal-sized?
│   │   ├─► YES ──────────────► KMeans
│   │   └─► NO (elliptical) ──► Gaussian Mixture (GMM)
│   │
│   └─► NO: Is data high-dimensional (D > 50)?
│       ├─► YES ──► Apply PCA first, then re-evaluate
│       └─► NO: Do clusters have uniform density?
│           ├─► YES ──► DBSCAN
│           └─► NO ───► OPTICS
│
└─► Is topology/connectivity important?
    ├─► Graph/Network data ──► Spectral Clustering
    └─► Spatial/Time-series ─► Agglomerative + Connectivity
```

## Quick Reference Table

| Data Geometry | Algorithm | Scalability |
|---------------|-----------|-------------|
| Spherical, known K | **KMeans** | ✅ O(NKI) |
| Elliptical/varying variance | **GMM** | ⚠️ O(NK²) |
| Arbitrary shapes, uniform density | **DBSCAN** | ✅ O(N log N) |
| Arbitrary shapes, varying density | **OPTICS** | ⚠️ O(N²) |
| Non-convex (rings, spirals) | **Spectral** | ❌ O(N³) |
| High-dimensional | **PCA + KMeans** | ✅ Linear |
| Spatial/temporal structure | **Agglomerative + Connectivity** | ⚠️ O(N²) |

**Golden Rule:** When in doubt, start with KMeans. If results look wrong, use this table to diagnose why and what to try next.
```

### Cell 26 (Code): Final Comparison Grid
**Task:** Generate comprehensive comparison visualization.

**Data:**
```python
# Challenging mixed dataset
np.random.seed(42)
# Two moons
moons, _ = make_moons(n_samples=400, noise=0.08)
# One blob offset
blob = np.random.randn(200, 2) * 0.3 + [0.5, 1.5]
# Noise
noise = np.random.uniform(-1.5, 2.5, size=(50, 2))

X_challenge = np.vstack([moons, blob, noise])
```

**Algorithms (6 total):**
1. KMeans (n_clusters=3)
2. GMM (n_components=3)
3. DBSCAN (eps=0.15, min_samples=5)
4. OPTICS (min_samples=5)
5. SpectralClustering (n_clusters=3)
6. AgglomerativeClustering (n_clusters=3)

**Visualization (2x3 grid):**
- Each subplot: scatter plot with cluster labels
- Title: Algorithm name
- Subtitle: Silhouette score (where applicable)

**Output:** `algorithm_comparison_final.png`

---

## VALIDATION CHECKLIST

The generated notebook must pass these checks:

### Code Execution
- [ ] All cells execute without errors in order
- [ ] No missing imports
- [ ] Random seeds set for reproducibility

### Visual Consistency
- [ ] All figures use `FIGURE_SIZE_*` constants
- [ ] Color palette consistent (`REGION_COLORS`, `POINT_COLORS`)
- [ ] Centroids use white-circle-black-cross style
- [ ] Transparent backgrounds on all GIF frames

### GIF Quality
- [ ] Loop infinitely (`loop=0`)
- [ ] Proper frame disposal (`disposal=2`)
- [ ] Pause frames at convergence
- [ ] Displayed inline after saving

### Content Completeness
- [ ] Every markdown cell has corresponding code cell
- [ ] All specified output files generated
- [ ] Metrics/scores printed where specified

---

## APPENDIX A: Mathematical Reference

### Inertia (KMeans Objective)
$$\text{Inertia} = \sum_{i=1}^{N} ||x_i - \mu_{c_i}||^2$$

### Silhouette Coefficient
$$s_i = \frac{b_i - a_i}{\max(a_i, b_i)}$$
- $a_i$ = mean distance to same-cluster points
- $b_i$ = mean distance to nearest other cluster

### Calinski-Harabasz Index
$$CH = \frac{B(K)/(K-1)}{W(K)/(N-K)}$$
- $B(K)$ = between-cluster sum of squares
- $W(K)$ = within-cluster sum of squares

### Gap Statistic
$$\text{Gap}(K) = \frac{1}{B}\sum_{b=1}^{B} \log(W_b^*(K)) - \log(W(K))$$

### Graph Laplacian (Spectral)
$$L = D - W$$
- $W$ = adjacency/similarity matrix
- $D$ = degree matrix (diagonal)

---

## APPENDIX B: Code Patterns

### Pattern: Step-by-Step KMeans
```python
def animate_kmeans(X, n_clusters, max_iter=15):
    """Animate KMeans by stepping one iteration at a time."""
    frames = []
    
    # Initialize with k-means++
    km = KMeans(n_clusters=n_clusters, n_init=1, max_iter=1, 
                random_state=RANDOM_STATE, init='k-means++')
    km.fit(X)
    centers = km.cluster_centers_.copy()
    
    for i in range(1, max_iter + 1):
        # One iteration from current centers
        km = KMeans(n_clusters=n_clusters, n_init=1, max_iter=1,
                    random_state=RANDOM_STATE, init=centers)
        km.fit(X)
        
        frame = create_frame(X, km.labels_, km.cluster_centers_, i)
        frames.append(frame)
        
        if np.allclose(centers, km.cluster_centers_, atol=1e-4):
            frames.extend([frame] * GIF_PAUSE_FRAMES)
            break
        
        centers = km.cluster_centers_.copy()
    
    return frames
```

### Pattern: 2x2 Grid Combination
```python
def combine_to_grid(frame_lists, titles=None):
    """Combine 4 animation lists into 2x2 grid animation."""
    # Pad to same length
    max_len = max(len(f) for f in frame_lists)
    for frames in frame_lists:
        while len(frames) < max_len:
            frames.append(frames[-1])
    
    combined = []
    for i in range(max_len):
        fig, axes = plt.subplots(2, 2, figsize=FIGURE_SIZE_GRID_2x2)
        fig.patch.set_alpha(0)
        
        for j, ax in enumerate(axes.flat):
            ax.imshow(frame_lists[j][i])
            ax.axis('off')
        
        plt.tight_layout(pad=0.5)
        combined.append(fig_to_pil(fig))
    
    return combined
```

---

## APPENDIX C: Expected Output Files

| Section | Filename | Type |
|---------|----------|------|
| 2 | `kmeans_animation.gif` | Animated GIF |
| 3 | `kmeans_failure_0.gif` | Animated GIF |
| 3 | `kmeans_failure_1.gif` | Animated GIF |
| 3 | `kmeans_failure_2.gif` | Animated GIF |
| 3 | `kmeans_failure_3.gif` | Animated GIF |
| 3 | `kmeans_failure_modes_combined.gif` | Animated GIF |
| 4 | `kmeans_solutions_combined.gif` | Animated GIF |
| 5 | `k_selection_comparison.png` | Static PNG |
| 6 | `pca_improvement.png` | Static PNG |
| 7 | `manifold_swiss_roll.png` | Static PNG |
| 8 | `spectral_vs_kmeans_circles.png` | Static PNG |
| 9 | `dbscan_noise_handling.png` | Static PNG |
| 10 | `optics_reachability.png` | Static PNG |
| 11 | `hierarchical_linkage_comparison.png` | Static PNG |
| 12 | `metrics_comparison.png` | Static PNG |
| 13 | `algorithm_comparison_final.png` | Static PNG |

---

*End of notebook generation prompt.*
