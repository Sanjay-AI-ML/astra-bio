# README – Lettuce Canopy Cover and Biomass Dataset by Saeed Karimzadeh, Ph.D.

## Dataset Description  
This dataset contains RGB canopy-cover images and corresponding biomass measurements of butterhead lettuce grown in a nutrient film technique (NFT) hydroponic system. Lettuce seedlings (14 days old at transplanting) were cultivated under controlled conditions as part of an experiment conducted at the Department of Biological and Agricultural Engineering, University of California, Davis.  

The experiment was designed and executed by Dr. Saeed Karimzadeh. A detailed description of the experimental setup and methodology is available in the associated PhD dissertation:  
👉 https://escholarship.org/uc/item/2x05k7r6

The experimental system consisted of a two-tier NFT rack supporting a total of 70 lettuce heads. Environmental variables and nutrient solution properties were continuously monitored throughout the experiment. The cultivation cycle ran from February 21, 2024, to March 23, 2024.  

---

## Dataset Contents  
The dataset includes the following components:  

- **Canopy Cover Images (folder: "Canopy Cover")  
  - Hourly overhead RGB images captured with an Intel® RealSense™ Depth Camera D405, positioned above the lettuce canopy.  
  - Images are labeled according to plant position (see Figure_1 for reference).  

- **Environmental and Nutrient Data ("Environment_Solution.xlsx")**  
  - Time-series data of environmental and solution dynamics, averaged at 30-minute intervals.  
  - Variables include:  
    - Water temperature  
    - Air temperature at upper and lower tiers
    - Relative humidity at upper and lower tiers 
    - Electrical conductivity (EC) of the nutrient solution  
    - Nutrient reservoir volume  

- **Biomass Measurements ("Biomass.xlsx")**  
  - Daily non-destructive weighting of fresh biomass (grams) for 18 reference lettuce heads (B22–B47, see Figure_1 for reference).  
  - Measurements span the entire cultivation cycle (Days After Transplanting, DAT).  

---

## Figures  
- **Figure 1. Experimental Design**  
  Growth rack layout with two cultivation levels, flow direction, sensor placement, nutrient reservoir, and camera position.  
- **Figure 2. Canopy Cover Labeling and Biomass Growth**  
  Example canopy image with labeled lettuce heads (B22–B47) and corresponding biomass time series.  

---

## Notes  
- Lettuce heads are consistently labeled (B22–B47) for cross-referencing between canopy images and biomass data.  
- Environmental and biomass datasets are aligned temporally with the image collection period.  

---
Contact Information:
For further information, please contact:
Dr. Saeed Karimzadeh
📧 skarimzadeh@ucdavis.edu
 | saeed.karimzadeh.civil@gmail.com