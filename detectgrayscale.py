''''
this file detects gray scale pictures
'''

from os import walk, path

from os.path import isfile, split, splitext, join

from PIL import Image

from multiprocessing import Process, Queue

from numpy import exp, array

import csv

__debug = False
__multiproc = True

#######################################  sigmoid #################################
##################################################################################

def sigmoid_int(value :int, offset : float = 0.0, steepness: float = 1.0 ):
	'''
	computes the sigmoid function on integer using offset and steepnes
	'''
	# compute the sigmoid value
	return 1.0 / (1.0 + exp(steepness*-value+offset))

#######################################  sigmoid #################################
##################################################################################
def is_gray_scale(image:Image, threshold: float =0.95):

    # create a mid centered sample
    # generat som ratio between 0 and 1 equally distant
    ratios = (step/40 for step in range(1,41))

    the_gray = 0
    the_color = 0

    # pick some pixels along the diagonal
    # process over all pixels to be picked
    for ratio in ratios:

        # get the x and y values
        x_val , y_val= [int(ratio*length) for length in image.shape]

        # get the reversed value of y
        y_rev = image.shape[1]-y_val

        # get a pair of pixel on the diagonal
        pixel_pair = [ image[x_val,y_choice] for y_choice in (y_val,y_rev) ]

        # check if the pixels are gray scale
        pixel_pair_check = sum( [ ch1/2 + ch2/2 - ch3 < 1 for ch1, ch2, ch3 in pixel_pair ] )

        # update the true and fasle count
        for a_check in pixel_pair_check : 
            the_gray += a_check
            the_color += not a_check

        # evalutate gray_scale probalility
            if sigmoid_int(value=the_gray,offset=5) > threshold : return True
            if sigmoid_int(value=the_color,offset=5) > threshold : return False

    return None

##########################  process a single image ###############################
##################################################################################

ill_files : list = []

# a helper function to process a single image.
def process_single_image( a_path, completion:str = "_filtered_by_red" ):

		# provide a feed back
		if __debug: 
			print ('[File]', a_path)
		else:
			print(".", end='')
		# open the file if possible
		try:
			image=Image.open(a_path)
			
		except:
			print( "could not open" , a_path)
			print( "aborting")
			ill_files.append("rm " + str(a_path))
			return  

		# provide with a feed back
		if __debug : 	
			print ("opened an", type(image))

		# filter the image
		filtered_image = melanineFilter(image)

		if __debug and False:
			exit()

		# save the result
		if True: 

			#create the completed path
			completed_path = create_completed_path(a_path=a_path, completion = completion)

			try:
				# try to save the file, if possible
				filtered_image.save(completed_path) 

			except BaseException as the_error:
				print ("Error: ", a_path, "," ,the_error)
				# note thefile
				ill_files.append("rm " + str(a_path))
				

############################# recursive processing ###############################
##################################################################################
def process_directory_or_file( directory_or_file: path='.', ):
	'''
	This processes all files recursively in all subfolder found if a folder is given as argumen
	If a file is given, only the file will be processed

	Arguments:
		directory_or_file [Path]: a path that can be a directory or a file
	return : nothing (file are saved here)
	'''
	# if the path leads to a file, so we process and save it directly then return 
	#if isfile(directory_or_file):
	print('')
	for root, directories, files  in walk(directory_or_file):
		#provide a feed back
		if __debug__ :
			print ('[root]', root)

		# generate the path to the files for processing
		absolute_pathes = ( join(root,aFile) for aFile in files )

		# switch for multiprocessing
		if  __multiproc :
			# generate the processes
			processes = ( Process(target=process_single_image, args=(a_file,"_filtered_by_red")) for a_file in absolute_pathes ) 

			# start the processes
			[ a_process.start() for a_process in processes ]

			# we may not join the processes since they don't produce any result
			if False : 
				[ a_process.join() for a_process in processes ]

		else : # this is for single thread processing
			[ process_single_image(a_path) for a_path in absolute_pathes] 
			
		for aDirectory in sorted(directories):
			# we recursively process the directories
			process_directory_or_file(join(root,aDirectory)) 

#a helper to create completed path

############################# main function ######################################
##################################################################################
# main function as a test candy
if __name__ == '__main__':

	thePaser = ArgumentParser(description="Filters out the non melanine(red) pixel from an image")
	
	thePaser.add_argument(
		'-p', '--path',
		metavar='path',
		type=str,
		help='provide a path containing images',
		required=True
	)

	# get the args
	input_args = thePaser.parse_args()

	# instantiate a queue for multiprocessing
	if _multiproc: 
		queue = Queue()

	# process the given path
	process_directory_or_file(input_args.path)
	
	with open("ill_files","w") as illfilespath:
		csv.writer(illfilespath, delimiter=' ').writerow(ill_files)